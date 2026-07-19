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
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.beneficio import (AcessoCreche, BeneficioCreche, CriancaCreche,
                                  StatusBeneficio)
from app.models.candidato import Candidato, PostoServico
from app.models.ficha import DadosPessoais, Endereco
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.validacao import cpf_valido

router = APIRouter(tags=["creche-publico"])

CODIGO_TTL_MIN = 15
SESSAO_TTL_H = 6


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


class IniciarIn(BaseModel):
    cpf: str
    email: str | None = None  # usado quando a base não tem e-mail do colaborador


@router.post("/creche/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    from app.core.config import ip_do_cliente
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    # anti-força-bruta e anti-spam de e-mail: por IP e por CPF
    exigir(f"creche-ini:ip:{ip_do_cliente(request) or '?'}", maximo=10, janela_s=900)
    exigir(f"creche-ini:cpf:{cpf}", maximo=5, janela_s=900)

    colaborador = _colaborador_por_cpf(db, cpf)
    # Resposta uniforme: mesmo se não achar, seguimos como se fôssemos enviar o
    # código, sem revelar se o CPF existe. Só enviamos de fato quando há e-mail.
    email_destino = None
    precisa_email = False
    if colaborador is not None:
        ben = _beneficio(db, colaborador)
        email_destino = (payload.email or "").strip() or colaborador.email
        if not email_destino:
            precisa_email = True
        else:
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
                      candidato_id=colaborador.id, detalhe={"cpf_final": cpf[-4:]})
            db.commit()
            _enviar_codigo(email_destino, colaborador.nome_completo, codigo)

    return {
        "precisa_email": precisa_email,
        # não revelamos existência: sempre dizemos que, se houver cadastro, o
        # código foi enviado
        "mensagem": "Se este CPF constar em nossa base, enviamos um código de "
                    "confirmação ao e-mail. Verifique também a caixa de spam.",
    }


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
    ben.email_confirmado = (payload.email or "").strip() or colaborador.email
    ben.email_confirmado_em = datetime.now(timezone.utc)
    if ben.status == StatusBeneficio.levantamento:
        pass  # mantém
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
