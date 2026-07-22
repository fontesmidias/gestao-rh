"""Link público único de levantamento do Reembolso-Creche (IN SEGES/MGI nº
147/2026). Todos os colaboradores recebem o MESMO link e se identificam por CPF.

Fluxo:
1. /creche/iniciar  {cpf}  -> localiza o colaborador na base, cria/recupera o
   benefício e envia um CÓDIGO de 6 dígitos ao e-mail (2FA). Se não houver
   e-mail na base, o colaborador informa um e-mail e o código vai para ele.
2. /creche/confirmar {cpf, email?, codigo} -> valida o código e devolve um TOKEN
   de sessão. Só APÓS confirmar é que os dados pré-preenchidos são revelados
   (LGPD: ninguém vê dado de terceiro digitando um CPF alheio).
3. Com o token: conferir dados, cadastrar crianças, subir certidão/guarda e
   enviar o levantamento para análise do RH.

A elegibilidade NÃO é revelada ao colaborador: o levantamento serve para a
análise interna de quem faz jus ao benefício, nos termos da IN 147/2026. Todos
preenchem; o RH decide.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from itsdangerous import BadSignature
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.beneficio import (AcessoCreche, BeneficioCreche, CriancaCreche,
                                  StatusBeneficio)
from app.models.candidato import Candidato, PostoServico
from app.models.ficha import DadosPessoais, Endereco
from app.services import kba, storage
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.validacao import cpf_valido

router = APIRouter(tags=["creche-publico"])

CODIGO_TTL_MIN = 15
SESSAO_TTL_H = 6
KBA_SALT = "creche-kba"


def _digitos(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _cpf_fmt(cpf: str) -> str:
    d = _digitos(cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def _colaborador_por_cpf(db: Session, cpf_digitos: str) -> Candidato | None:
    """Colaborador (situação preenchida) cujo CPF bate. Prioriza registros já
    colaboradores; ignora candidatos em admissão pura."""
    fmt = _cpf_fmt(cpf_digitos)
    cands = db.scalars(select(Candidato).where(Candidato.cpf.in_([fmt, cpf_digitos]))).all()
    # prioriza quem já é colaborador
    cands.sort(key=lambda c: (c.situacao is None, c.criado_em), reverse=False)
    for c in cands:
        if c.situacao:
            return c
    return cands[0] if cands else None


def _beneficio(db: Session, candidato: Candidato) -> BeneficioCreche:
    ben = db.scalar(select(BeneficioCreche)
                    .where(BeneficioCreche.candidato_id == candidato.id))
    if ben is None:
        ben = BeneficioCreche(candidato_id=candidato.id)
        db.add(ben)
        db.flush()
    return ben


def _sessao_valida(db: Session, token: str) -> tuple[AcessoCreche, BeneficioCreche] | None:
    ac = db.scalar(select(AcessoCreche).where(AcessoCreche.token_hash == _hash(token)))
    if ac is None or ac.confirmado_em is None:
        return None
    if ac.expira_em < datetime.now(timezone.utc):
        return None
    ben = db.get(BeneficioCreche, ac.beneficio_id)
    return (ac, ben) if ben else None


def _requer_sessao(token: str, db: Session) -> tuple[AcessoCreche, BeneficioCreche]:
    r = _sessao_valida(db, token)
    if r is None:
        raise HTTPException(status_code=401, detail="sessao_invalida")
    return r


# --------------------------------------------------------------------------
# 1) iniciar: CPF -> envia código 2FA
# --------------------------------------------------------------------------


def _gerar_e_enviar_codigo(db: Session, colaborador: Candidato,
                           ben: BeneficioCreche, email_destino: str) -> None:
    """Cria um AcessoCreche pendente e envia o código 2FA ao e-mail. O e-mail é
    disparado APÓS o commit (SMTP fora não desfaz o registro)."""
    codigo = f"{secrets.randbelow(10**6):06d}"
    ac = AcessoCreche(
        beneficio_id=ben.id,
        token_hash=_hash(secrets.token_urlsafe(32)),  # placeholder até confirmar
        codigo_hash=_hash(codigo),
        codigo_expira_em=datetime.now(timezone.utc) + timedelta(minutes=CODIGO_TTL_MIN),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H),
    )
    db.add(ac)
    registrar(db, "creche_codigo_enviado", ator="colaborador",
              candidato_id=colaborador.id, detalhe={"cpf_final": _digitos(colaborador.cpf or "")[-4:]})
    db.commit()
    _enviar_codigo(email_destino, colaborador.nome_completo, codigo)


class IniciarIn(BaseModel):
    cpf: str


@router.post("/creche/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """CPF -> se o colaborador existe E tem e-mail, envia o código 2FA. Caso
    contrário (sem e-mail OU CPF fora da base), responde EXATAMENTE o mesmo — sem
    revelar nada (anti-enumeração). Quem não recebeu o código usa o fluxo de
    verificação de identidade (KBA) para cadastrar/atualizar o e-mail."""
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    exigir(f"creche-ini:ip:{ip_do_cliente(request) or '?'}", maximo=10, janela_s=900)
    exigir(f"creche-ini:cpf:{cpf}", maximo=5, janela_s=900)

    colaborador = _colaborador_por_cpf(db, cpf)
    if colaborador is not None and colaborador.email:
        ben = _beneficio(db, colaborador)
        db.commit()
        _gerar_e_enviar_codigo(db, colaborador, ben, colaborador.email)

    # Resposta SEMPRE idêntica — não distingue base-com-email, base-sem-email nem
    # fora-da-base. `pode_verificar_identidade` está sempre disponível.
    return {
        "pode_verificar_identidade": True,
        "mensagem": "Se este CPF constar em nossa base e houver e-mail cadastrado, "
                    "enviamos um código de confirmação. Verifique também a caixa de "
                    "spam. Não recebeu? Você pode confirmar sua identidade.",
    }


# --------------------------------------------------------------------------
# 1b) verificação de identidade (KBA) para quem não tem e-mail cadastrado:
#     CPF -> perguntas -> respostas -> cadastrar/atualizar e-mail -> código.
#     Reaproveita a KBA da entrada de admissão (app/services/kba.py).
# --------------------------------------------------------------------------


class KbaIniciarIn(BaseModel):
    cpf: str


@router.post("/creche/kba/iniciar")
def kba_iniciar(payload: KbaIniciarIn, request: Request,
                db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    ip = ip_do_cliente(request) or "-"
    exigir(f"creche-kba:ip:{ip}", maximo=10, janela_s=900)
    if kba.bloqueado(f"creche:cpf:{cpf}") or kba.bloqueado(f"creche:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    colaborador = _colaborador_por_cpf(db, cpf)
    # CPF fora da base / sem dados suficientes -> pool genérico (gabarito
    # impossível): resposta uniforme, nada revela.
    return kba.montar_desafio(db, colaborador, KBA_SALT, extra_payload={"cpf": cpf})


class KbaResponderIn(BaseModel):
    desafio: str
    respostas: dict[str, str]


@router.post("/creche/kba/responder")
def kba_responder(payload: KbaResponderIn, request: Request,
                  db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.desafio, max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="desafio_expirado")
    cpf = dados["cpf"]
    if kba.bloqueado(f"creche:cpf:{cpf}") or kba.bloqueado(f"creche:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    if not kba.conferir_respostas(dados["gabarito"], payload.respostas):
        kba.registrar_falha(f"creche:cpf:{cpf}", f"creche:ip:{ip}")
        registrar(db, "creche_kba_falhou", ator="colaborador",
                  detalhe={"cpf_final": cpf[-4:], "ip": ip})
        db.commit()
        raise HTTPException(status_code=422, detail="nao_confirmado")
    colaborador = _colaborador_por_cpf(db, cpf)
    registrar(db, "creche_kba_ok", ator="colaborador",
              candidato_id=colaborador.id if colaborador else None, detalhe={"ip": ip})
    db.commit()
    # token curto que autoriza cadastrar/atualizar o e-mail
    autorizacao = kba.serializer(KBA_SALT).dumps({"cpf": cpf, "kba_ok": True})
    return {"autorizacao": autorizacao}


class KbaDefinirEmailIn(BaseModel):
    autorizacao: str
    email: str


@router.post("/creche/kba/definir-email")
def kba_definir_email(payload: KbaDefinirEmailIn, request: Request,
                      db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.autorizacao, max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="autorizacao_expirada")
    if not dados.get("kba_ok"):
        raise HTTPException(status_code=422, detail="autorizacao_invalida")
    email = (payload.email or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="email_invalido")
    colaborador = _colaborador_por_cpf(db, dados["cpf"])
    if colaborador is None:
        # KBA só passa para CPF real; guarda de segurança adicional.
        raise HTTPException(status_code=422, detail="nao_confirmado")
    ben = _beneficio(db, colaborador)
    # atualiza o e-mail do cadastro (identidade já confirmada pela KBA)
    colaborador.email = email
    ben.email_confirmado = email
    registrar(db, "creche_email_atualizado_kba", ator="colaborador",
              candidato_id=colaborador.id, detalhe={"ip": ip})
    db.commit()
    _gerar_e_enviar_codigo(db, colaborador, ben, email)
    return {"ok": True}


def _enviar_codigo(email: str, nome: str, codigo: str) -> None:
    enviar_email(
        email,
        "Green House — código para o levantamento do Reembolso-Creche",
        f"Olá, {nome.split()[0].title()}!\n\n"
        f"Seu código de confirmação é: {codigo}\n\n"
        "Ele vale por 15 minutos. Se você não solicitou, ignore esta mensagem.\n\n"
        "IMPORTANTE: verifique também a sua caixa de SPAM/lixo eletrônico — às "
        "vezes a mensagem chega lá.\n",
        html_moderno(
            "Seu código de confirmação",
            [
                f"Olá, <strong>{nome.split()[0].title()}</strong>!",
                "Use o código abaixo para confirmar sua identidade no levantamento "
                "do Reembolso-Creche (IN SEGES/MGI nº 147/2026):",
                f"<div style='font-size:2rem;font-weight:800;letter-spacing:.3em;"
                f"text-align:center;margin:1rem 0;color:#0a8f46'>{codigo}</div>",
                "O código vale por 15 minutos. <strong>Verifique também a sua caixa "
                "de spam</strong> — a mensagem pode ter ido para lá.",
            ],
        ),
    )


# --------------------------------------------------------------------------
# 2) confirmar: código -> token de sessão
# --------------------------------------------------------------------------


class ConfirmarIn(BaseModel):
    cpf: str
    codigo: str
    email: str | None = None


@router.post("/creche/confirmar")
def confirmar(payload: ConfirmarIn, db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    # código de 6 dígitos: 10 tentativas por CPF na janela e acabou
    exigir(f"creche-2fa:cpf:{cpf}", maximo=10, janela_s=900)
    colaborador = _colaborador_por_cpf(db, cpf)
    if colaborador is None:
        raise HTTPException(status_code=422, detail="codigo_invalido")
    ben = _beneficio(db, colaborador)
    # pega o acesso mais recente com código ainda válido
    ac = db.scalars(
        select(AcessoCreche)
        .where(AcessoCreche.beneficio_id == ben.id,
               AcessoCreche.confirmado_em.is_(None))
        .order_by(AcessoCreche.criado_em.desc())
    ).first()
    if (ac is None or ac.codigo_hash != _hash(payload.codigo.strip())
            or ac.codigo_expira_em < datetime.now(timezone.utc)):
        raise HTTPException(status_code=422, detail="codigo_invalido")

    # emite token de sessão real
    token = secrets.token_urlsafe(32)
    ac.token_hash = _hash(token)
    ac.confirmado_em = datetime.now(timezone.utc)
    ac.expira_em = datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H)
    # o e-mail já foi cadastrado no /iniciar (com e-mail) ou na KBA; o campo do
    # payload permanece só como fallback de compatibilidade.
    ben.email_confirmado = colaborador.email or (payload.email or "").strip() or ben.email_confirmado
    ben.email_confirmado_em = datetime.now(timezone.utc)
    registrar(db, "creche_2fa_confirmado", ator="colaborador",
              candidato_id=colaborador.id)
    db.commit()
    return {"token": token}


# --------------------------------------------------------------------------
# 3) sessão: dados pré-preenchidos, crianças, upload, envio
# --------------------------------------------------------------------------


def _dump_crianca(c: CriancaCreche) -> dict:
    return {"id": c.id, "nome": c.nome, "data_nascimento": c.data_nascimento,
            "parentesco": c.parentesco, "tipo_comprovante": c.tipo_comprovante,
            "tem_certidao": bool(c.certidao_key), "tem_guarda": bool(c.guarda_key)}


@router.get("/creche/sessao/{token}")
def ver_sessao(token: str, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    col = db.get(Candidato, ben.candidato_id)
    p = db.get(DadosPessoais, col.id)
    e = db.get(Endereco, col.id)
    # dados pré-preenchidos da base — o colaborador confere e confirma/atualiza
    return {
        "status": ben.status,
        "nome_completo": col.nome_completo,
        "cpf": col.cpf,
        "email": ben.email_confirmado or col.email,
        "telefone": ben.telefone or col.celular_whatsapp,
        "cargo": col.cargo_funcao,
        "posto": (db.get(PostoServico, col.posto_servico_id).nome
                  if col.posto_servico_id else None),
        "endereco": (e.logradouro_numero_complemento if e else None),
        "cidade": (e.cidade if e else None),
        "dados_conferidos": ben.dados_conferidos_em is not None,
        "criancas": [_dump_crianca(c) for c in ben.criancas],
        "editavel": ben.status in (StatusBeneficio.levantamento,),
        # Se o RH devolveu para correção, o colaborador vê o motivo ao reabrir
        # (feedback 2026-07-21) — só faz sentido enquanto estiver editável.
        "motivo_devolucao": (ben.motivo_devolucao
                             if ben.status == StatusBeneficio.levantamento else None),
    }


class ConferirDadosIn(BaseModel):
    email: str | None = None
    telefone: str | None = None


@router.put("/creche/sessao/{token}/dados")
def conferir_dados(token: str, payload: ConferirDadosIn, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    if payload.email is not None:
        ben.email_confirmado = payload.email.strip() or ben.email_confirmado
    if payload.telefone is not None:
        ben.telefone = payload.telefone.strip() or None
    ben.dados_conferidos_em = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


class CriancaIn(BaseModel):
    nome: str
    data_nascimento: str  # dd/mm/aaaa
    parentesco: str       # filho | enteado | guarda
    tipo_comprovante: str | None = None  # declaracao | nota_fiscal


@router.post("/creche/sessao/{token}/criancas", status_code=201)
def add_crianca(token: str, payload: CriancaIn, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    if ben.status != StatusBeneficio.levantamento:
        raise HTTPException(status_code=409, detail="levantamento_encerrado")
    if payload.parentesco not in ("filho", "enteado", "guarda"):
        raise HTTPException(status_code=422, detail="parentesco_invalido")
    c = CriancaCreche(
        beneficio_id=ben.id, nome=payload.nome.strip(),
        data_nascimento=payload.data_nascimento.strip(),
        parentesco=payload.parentesco,
        tipo_comprovante=payload.tipo_comprovante)
    db.add(c)
    db.commit()
    return _dump_crianca(c)


@router.delete("/creche/sessao/{token}/criancas/{crianca_id}", status_code=204)
def del_crianca(token: str, crianca_id: str, db: Session = Depends(get_db)) -> None:
    _, ben = _requer_sessao(token, db)
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    db.delete(c)
    db.commit()


@router.post("/creche/sessao/{token}/criancas/{crianca_id}/documento")
async def subir_documento(token: str, crianca_id: str, tipo: str, arquivo: UploadFile,
                          db: Session = Depends(get_db)) -> dict:
    """Sobe certidão de nascimento (tipo=certidao) ou guarda judicial
    (tipo=guarda) da criança."""
    _, ben = _requer_sessao(token, db)
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=422, detail="arquivo_vazio")
    ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5] or "bin"
    key = f"creche/{ben.id}/{crianca_id}/{tipo}.{ext}"
    storage.salvar(key, conteudo, arquivo.content_type or "application/octet-stream")
    if tipo == "certidao":
        c.certidao_key = key
    else:
        c.guarda_key = key
    db.commit()
    return _dump_crianca(c)


@router.post("/creche/sessao/{token}/enviar")
def enviar(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Fecha o levantamento e envia para análise do RH."""
    _, ben = _requer_sessao(token, db)
    if not ben.criancas:
        raise HTTPException(status_code=422, detail="sem_criancas")
    faltando = [c.nome for c in ben.criancas if not c.certidao_key]
    if faltando:
        raise HTTPException(status_code=422,
                            detail={"erro": "certidao_faltando", "criancas": faltando})
    ben.status = StatusBeneficio.em_analise
    ben.enviado_em = datetime.now(timezone.utc)
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_levantamento_enviado", ator="colaborador",
              candidato_id=col.id, detalhe={"criancas": len(ben.criancas)})
    db.commit()
    return {"status": ben.status}


@router.post("/creche/sessao/{token}/sem-direito")
def declarar_sem_direito(token: str, db: Session = Depends(get_db)) -> dict:
    """O colaborador declara que NÃO tem dependentes que dão direito ao benefício
    (feedback 2026-07-21). Some da fila de ação, mas fica no relatório do RH como
    'consultado e não pediu'. Só quando ainda está preenchendo (levantamento)."""
    _, ben = _requer_sessao(token, db)
    if ben.status != StatusBeneficio.levantamento:
        raise HTTPException(status_code=409, detail="levantamento_encerrado")
    ben.status = StatusBeneficio.sem_direito_declarado
    ben.sem_direito_em = datetime.now(timezone.utc)
    ben.sem_direito_por = "colaborador"
    registrar(db, "creche_sem_direito", ator="colaborador",
              candidato_id=ben.candidato_id, detalhe={"por": "colaborador"})
    db.commit()
    return {"status": ben.status}


# --------------------------------------------------------------------------
# Assinatura do requerimento pela plataforma (após aprovação do RH). O
# colaborador assina na PRÓPRIA sessão de creche (já autenticada por 2FA);
# depois o RH contra-assina pela fila /rh/minhas-assinaturas.
# --------------------------------------------------------------------------


def _etapa_colaborador(db: Session, ben: BeneficioCreche):
    """A etapa (ordem 1) do colaborador no roteiro do requerimento, se houver."""
    from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                                   SolicitacaoAssinatura)
    from app.services.roteiro_assinatura import tem_roteiro
    sol = tem_roteiro(db, ben.candidato_id)
    if sol is None or sol.origem != "creche_requerimento":
        return None, None
    etapa = db.scalar(select(EtapaAssinatura)
                      .where(EtapaAssinatura.solicitacao_id == sol.id,
                             EtapaAssinatura.ordem == 1))
    return sol, etapa


@router.get("/creche/sessao/{token}/requerimento")
def status_requerimento(token: str, db: Session = Depends(get_db)) -> dict:
    """Diz à sessão se há requerimento a assinar (benefício aprovado), se o
    colaborador já assinou e se o documento foi concluído."""
    from app.models.solicitacao_assinatura import StatusSolicitacao
    _, ben = _requer_sessao(token, db)
    sol, etapa = _etapa_colaborador(db, ben)
    if sol is None or etapa is None:
        return {"disponivel": False}
    return {
        "disponivel": True,
        "assinado": etapa.assinado_em is not None,
        "na_vez": etapa.ordem == sol.etapa_atual_ordem
                  and sol.status == StatusSolicitacao.aguardando,
        "concluido": sol.status == StatusSolicitacao.concluida,
    }


@router.post("/creche/sessao/{token}/assinar-requerimento")
def assinar_requerimento(token: str, request: Request,
                         db: Session = Depends(get_db)) -> dict:
    """Registra a assinatura do colaborador no requerimento — a sessão de creche
    já é o 2º fator (2FA por código no e-mail). Idempotente e serializado pelo
    avancar_solicitacao (correções C3/C7 do multi-signatário)."""
    import hashlib

    from app.models.solicitacao_assinatura import StatusSolicitacao
    from app.services.creche_pdf import gerar_requerimento_creche
    from app.services.roteiro_assinatura import avancar_solicitacao
    _, ben = _requer_sessao(token, db)
    sol, etapa = _etapa_colaborador(db, ben)
    if sol is None or etapa is None:
        raise HTTPException(status_code=404, detail="requerimento_indisponivel")
    if etapa.assinado_em is not None:
        raise HTTPException(status_code=409, detail="ja_assinado")
    if sol.status != StatusSolicitacao.aguardando or etapa.ordem != sol.etapa_atual_ordem:
        raise HTTPException(status_code=409, detail="fora_da_vez")
    col = db.get(Candidato, ben.candidato_id)
    # hash do documento SEM blocos (evidência) — mesmo critério do fluxo do wizard
    pdf_sem_bloco = gerar_requerimento_creche(db, ben)
    agora = datetime.now(timezone.utc)
    etapa.assinado_em = agora
    etapa.assinante_nome = col.nome_completo
    etapa.assinante_cpf = col.cpf
    etapa.ip = ip_do_cliente(request)
    etapa.user_agent = request.headers.get("user-agent", "")[:400]
    etapa.prova_metodo = "otp_creche"
    etapa.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
    registrar(db, "creche_requerimento_assinado", ator="colaborador",
              candidato_id=col.id, detalhe={"solicitacao": str(sol.id)})
    db.commit()
    resultado = avancar_solicitacao(db, sol.id)
    db.commit()
    return {"assinado": True, "concluido": resultado["concluida"]}


# ==========================================================================
# Coleta de creche DENTRO da admissão: o candidato já autenticado pelo link
# mágico informa as crianças, se o posto dele dá direito. Sem 2FA (a admissão
# já autentica). Reaproveita BeneficioCreche/CriancaCreche.
# ==========================================================================


@router.get("/c/{token}/creche")
def creche_admissao_status(token: str, db: Session = Depends(get_db)) -> dict:
    """Diz ao wizard de admissão se o posto do candidato dá direito ao
    reembolso-creche e devolve as crianças já informadas. Se o posto não é
    elegível, o bloco nem aparece."""
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    posto = db.get(PostoServico, cand.posto_servico_id) if cand.posto_servico_id else None
    elegivel = bool(posto and posto.da_direito_creche)
    ben = db.scalar(select(BeneficioCreche)
                    .where(BeneficioCreche.candidato_id == cand.id)) if elegivel else None
    return {
        "posto_da_direito": elegivel,
        "posto": posto.nome if posto else None,
        "criancas": [_dump_crianca(c) for c in ben.criancas] if ben else [],
    }


@router.post("/c/{token}/creche/criancas", status_code=201)
def creche_admissao_add(token: str, payload: CriancaIn, db: Session = Depends(get_db)) -> dict:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    posto = db.get(PostoServico, cand.posto_servico_id) if cand.posto_servico_id else None
    if not (posto and posto.da_direito_creche):
        raise HTTPException(status_code=409, detail="posto_nao_elegivel")
    if payload.parentesco not in ("filho", "enteado", "guarda"):
        raise HTTPException(status_code=422, detail="parentesco_invalido")
    ben = db.scalar(select(BeneficioCreche).where(BeneficioCreche.candidato_id == cand.id))
    if ben is None:
        ben = BeneficioCreche(candidato_id=cand.id, email_confirmado=cand.email)
        db.add(ben)
        db.flush()
    c = CriancaCreche(beneficio_id=ben.id, nome=payload.nome.strip(),
                      data_nascimento=payload.data_nascimento.strip(),
                      parentesco=payload.parentesco, tipo_comprovante=payload.tipo_comprovante)
    db.add(c)
    registrar(db, "creche_crianca_na_admissao", ator="candidato", candidato_id=cand.id)
    db.commit()
    return _dump_crianca(c)


@router.delete("/c/{token}/creche/criancas/{crianca_id}", status_code=204)
def creche_admissao_del(token: str, crianca_id: str, db: Session = Depends(get_db)) -> None:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    c = db.get(CriancaCreche, crianca_id)
    ben = db.get(BeneficioCreche, c.beneficio_id) if c else None
    if c is None or ben is None or ben.candidato_id != cand.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    db.delete(c)
    db.commit()


@router.post("/c/{token}/creche/criancas/{crianca_id}/documento")
async def creche_admissao_doc(token: str, crianca_id: str, tipo: str, arquivo: UploadFile,
                              db: Session = Depends(get_db)) -> dict:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    c = db.get(CriancaCreche, crianca_id)
    ben = db.get(BeneficioCreche, c.beneficio_id) if c else None
    if c is None or ben is None or ben.candidato_id != cand.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=422, detail="arquivo_vazio")
    ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5] or "bin"
    key = f"creche/{ben.id}/{crianca_id}/{tipo}.{ext}"
    storage.salvar(key, conteudo, arquivo.content_type or "application/octet-stream")
    if tipo == "certidao":
        c.certidao_key = key
    else:
        c.guarda_key = key
    db.commit()
    return _dump_crianca(c)
