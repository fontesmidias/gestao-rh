"""Portal do colaborador — `/meu` (Onda B).

Uma porta só para tudo que é do colaborador: hoje o desenvolvimento (cursos,
certificados, reciclagem de brigada), amanhã o creche e a avaliação. O oposto
de `/creche`, `/desenvolvimento`, `/brigada` como portas separadas — que em
seis meses deixaria a pessoa sem saber qual é a dela.

**O gate é o mesmo do creche**, que já está testado em produção: CPF → 2FA por
e-mail; quem não tem e-mail passa pela KBA (`app/services/kba.py`) e cadastra o
seu. A resposta do `/iniciar` NUNCA revela se o CPF está na base
(anti-enumeração) — é idêntica para base-com-email, base-sem-email e
fora-da-base.

A KBA usa dados NATIVOS do `Candidato` (nascimento + sobrenome), então funciona
para quem foi importado do Tirvu e nunca preencheu ficha — que é a maioria dos
~1.200 colaboradores.
"""

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from itsdangerous import BadSignature
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico
from app.models.desenvolvimento import (AcessoPortal, ArquivoDesenvolvimento,
                                        RegistroDesenvolvimento,
                                        SensibilidadeDoc, StatusRegistro,
                                        TipoDesenvolvimento)
from app.services import kba, storage
from app.services.auditoria import registrar
from app.services.desenvolvimento import (calcular_validade, meses_validade_de,
                                          situacao_validade, tipos_do_cargo)
from app.services.validacao import cpf_valido

router = APIRouter(tags=["portal-colaborador"])

CODIGO_TTL_MIN = 15
SESSAO_TTL_H = 6
KBA_SALT = "portal-kba"

# Sensibilidade por papel do documento — governa o roteamento da IA (LGPD).
SENSIBILIDADE_PAPEL = {
    "identidade": SensibilidadeDoc.identidade,
    "aso": SensibilidadeDoc.saude,
}
PAPEIS_VALIDOS = ("identidade", "certificado_formacao", "certificado_reciclagem",
                  "aso", "outro")
EXT_ACEITAS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "doc", "docx"}
TAMANHO_MAX = 10 * 1024 * 1024  # 10 MB, como no currículo do Banco de Talentos


def _digitos(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def _colaborador_por_cpf(db: Session, cpf: str) -> Candidato | None:
    """Colaborador ATIVO por CPF. Quem está em admissão (situacao NULL) não
    entra aqui — o wizard dele é outro."""
    for c in db.scalars(select(Candidato).where(Candidato.situacao.isnot(None))):
        if _digitos(c.cpf or "") == cpf:
            return c
    return None


def _sessao(db: Session, token: str) -> tuple[AcessoPortal, Candidato]:
    ac = db.scalar(select(AcessoPortal).where(AcessoPortal.token_hash == _hash(token)))
    if (ac is None or ac.confirmado_em is None
            or ac.expira_em < datetime.now(timezone.utc)):
        raise HTTPException(status_code=401, detail="sessao_invalida")
    col = db.get(Candidato, ac.candidato_id)
    if col is None:
        raise HTTPException(status_code=401, detail="sessao_invalida")
    return ac, col


# ---------------------------------------------------------------------------
# 1) entrada: CPF -> código por e-mail (ou KBA para quem não tem e-mail)
# ---------------------------------------------------------------------------


class IniciarIn(BaseModel):
    cpf: str


def _gerar_e_enviar_codigo(db: Session, col: Candidato, email: str) -> None:
    codigo = f"{secrets.randbelow(10**6):06d}"
    db.add(AcessoPortal(
        candidato_id=col.id,
        token_hash=_hash(secrets.token_urlsafe(32)),  # placeholder até confirmar
        codigo_hash=_hash(codigo),
        codigo_expira_em=datetime.now(timezone.utc) + timedelta(minutes=CODIGO_TTL_MIN),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H)))
    registrar(db, "portal_codigo_enviado", ator="colaborador", candidato_id=col.id)
    db.commit()
    _enviar_codigo(email, col.nome_completo, codigo)


def _enviar_codigo(email: str, nome: str, codigo: str) -> None:
    from app.services.email import enviar_email, html_moderno
    primeiro = (nome or "").split()[0].title() if nome else ""
    enviar_email(
        email, "Green House — seu código de acesso",
        f"Olá, {primeiro}!\n\nSeu código de acesso é {codigo}.\n"
        f"Ele vale por {CODIGO_TTL_MIN} minutos.\n\n"
        "Se não foi você que pediu, ignore este e-mail.\n",
        html_moderno("Seu código de acesso",
                     [f"Olá, <strong>{primeiro}</strong>!",
                      "Use o código abaixo para entrar no seu portal.",
                      f"O código vale por {CODIGO_TTL_MIN} minutos."],
                     destaque=codigo))


@router.post("/portal/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """CPF → manda o código a quem tem e-mail. A resposta é SEMPRE a mesma, não
    importa se o CPF existe: quem não recebeu usa a verificação de identidade."""
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    exigir(f"portal-ini:ip:{ip_do_cliente(request) or '?'}", maximo=10, janela_s=900)
    exigir(f"portal-ini:cpf:{cpf}", maximo=5, janela_s=900)

    col = _colaborador_por_cpf(db, cpf)
    if col is not None and col.email:
        _gerar_e_enviar_codigo(db, col, col.email)

    return {
        "pode_verificar_identidade": True,
        "mensagem": "Se este CPF constar em nossa base e houver e-mail cadastrado, "
                    "enviamos um código de confirmação. Verifique também a caixa de "
                    "spam. Não recebeu? Você pode confirmar sua identidade.",
    }


class ConfirmarIn(BaseModel):
    cpf: str
    codigo: str


@router.post("/portal/confirmar")
def confirmar(payload: ConfirmarIn, db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    exigir(f"portal-2fa:cpf:{cpf}", maximo=10, janela_s=900)
    col = _colaborador_por_cpf(db, cpf)
    if col is None:
        raise HTTPException(status_code=422, detail="codigo_invalido")
    ac = db.scalars(
        select(AcessoPortal)
        .where(AcessoPortal.candidato_id == col.id,
               AcessoPortal.confirmado_em.is_(None))
        .order_by(AcessoPortal.criado_em.desc())).first()
    if (ac is None or ac.codigo_hash != _hash(payload.codigo.strip())
            or ac.codigo_expira_em < datetime.now(timezone.utc)):
        raise HTTPException(status_code=422, detail="codigo_invalido")

    token = secrets.token_urlsafe(32)
    ac.token_hash = _hash(token)
    ac.confirmado_em = datetime.now(timezone.utc)
    ac.expira_em = datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H)
    registrar(db, "portal_2fa_confirmado", ator="colaborador", candidato_id=col.id)
    db.commit()
    return {"token": token}


# ---------------------------------------------------------------------------
# 1b) KBA — quem não tem e-mail cadastrado prova quem é e cadastra o seu
# ---------------------------------------------------------------------------


class KbaIniciarIn(BaseModel):
    cpf: str


@router.post("/portal/kba/iniciar")
def kba_iniciar(payload: KbaIniciarIn, request: Request,
                db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    ip = ip_do_cliente(request) or "-"
    exigir(f"portal-kba:ip:{ip}", maximo=10, janela_s=900)
    if kba.bloqueado(f"portal:cpf:{cpf}") or kba.bloqueado(f"portal:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    col = _colaborador_por_cpf(db, cpf)
    # CPF fora da base cai no pool genérico (gabarito impossível): a resposta é
    # uniforme e não revela nada.
    return kba.montar_desafio(db, col, KBA_SALT, extra_payload={"cpf": cpf})


class KbaResponderIn(BaseModel):
    desafio: str
    respostas: dict[str, str]


@router.post("/portal/kba/responder")
def kba_responder(payload: KbaResponderIn, request: Request,
                  db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.desafio,
                                               max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="desafio_expirado")
    cpf = dados.get("cpf", "")
    if kba.bloqueado(f"portal:cpf:{cpf}") or kba.bloqueado(f"portal:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    if not kba.conferir_respostas(dados.get("gabarito", {}), payload.respostas):
        kba.registrar_falha(f"portal:cpf:{cpf}", f"portal:ip:{ip}")
        raise HTTPException(status_code=422, detail="respostas_incorretas")
    autorizacao = kba.serializer(KBA_SALT).dumps({"cpf": cpf, "ok": True})
    return {"autorizacao": autorizacao}


class KbaEmailIn(BaseModel):
    autorizacao: str
    email: str


@router.post("/portal/kba/definir-email")
def kba_definir_email(payload: KbaEmailIn, db: Session = Depends(get_db)) -> dict:
    """Com a identidade provada, cadastra/atualiza o e-mail e manda o código."""
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.autorizacao,
                                               max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="autorizacao_expirada")
    if not dados.get("ok"):
        raise HTTPException(status_code=422, detail="autorizacao_invalida")
    email = (payload.email or "").strip()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="email_invalido")
    col = _colaborador_por_cpf(db, dados.get("cpf", ""))
    if col is None:
        # resposta uniforme: quem provou identidade de um CPF fora da base vê o
        # mesmo que quem provou de um CPF real
        return {"enviado": True}
    col.email = email
    registrar(db, "portal_email_cadastrado", ator="colaborador", candidato_id=col.id,
              detalhe={"via": "kba"})
    db.commit()
    _gerar_e_enviar_codigo(db, col, email)
    return {"enviado": True}


# ---------------------------------------------------------------------------
# 2) a home: quem sou eu e o que está pendente
# ---------------------------------------------------------------------------


def _dump_registro(db: Session, r: RegistroDesenvolvimento) -> dict:
    return {
        "id": str(r.id),
        "tipo": r.tipo.nome if r.tipo else None,
        "tipo_id": str(r.tipo_id),
        "titulo": r.titulo,
        "instituicao": r.instituicao,
        "carga_horaria": r.carga_horaria,
        "concluido_em": r.concluido_em.isoformat() if r.concluido_em else None,
        "validade_ate": r.validade_ate.isoformat() if r.validade_ate else None,
        "situacao_validade": situacao_validade(r),
        "status": r.status.value,
        "critico": bool(r.tipo and r.tipo.critico),
        # o motivo da recusa é VISÍVEL ao colaborador (decisão do Bruno):
        # recusa sem motivo gera ligação para o RH
        "motivo_recusa": r.motivo_recusa,
        "documentos": [{"id": str(a.id), "papel": a.papel,
                        "nome": a.nome_original} for a in r.arquivos],
        "criado_em": r.criado_em.isoformat() if r.criado_em else None,
    }


@router.get("/portal/sessao/{token}")
def ver_sessao(token: str, db: Session = Depends(get_db)) -> dict:
    """Home do portal: os dados da pessoa, o que ela já mandou e o que falta.

    A tela inicial é a lista de PENDÊNCIAS dela, não um menu — quem entra quer
    resolver algo. Sem pendência, vê o próprio histórico.
    """
    _, col = _sessao(db, token)
    registros = db.scalars(
        select(RegistroDesenvolvimento)
        .where(RegistroDesenvolvimento.candidato_id == col.id)
        .order_by(RegistroDesenvolvimento.criado_em.desc())).all()

    pendencias = []
    for r in registros:
        sit = situacao_validade(r)
        if r.status == StatusRegistro.devolvido:
            pendencias.append({"tipo": "devolvido", "registro_id": str(r.id),
                               "titulo": r.titulo or (r.tipo.nome if r.tipo else ""),
                               "detalhe": r.motivo_recusa or
                                          "O RH pediu uma correção neste envio."})
        elif sit in ("a_vencer", "vencido") and r.status == StatusRegistro.validado:
            dias = (r.validade_ate - date.today()).days
            pendencias.append({
                "tipo": "vencimento", "registro_id": str(r.id),
                "titulo": r.titulo or (r.tipo.nome if r.tipo else ""),
                "detalhe": (f"Vence em {dias} dias." if dias >= 0
                            else f"Venceu há {-dias} dias."),
                "urgente": dias < 0})

    posto = db.get(PostoServico, col.posto_servico_id) if col.posto_servico_id else None
    return {
        "nome": col.nome_completo,
        "primeiro_nome": (col.nome_completo or "").split()[0].title(),
        "cargo": col.cargo_funcao,
        "posto": posto.nome if posto else None,
        "email": col.email,
        "matricula": col.matricula,
        "pendencias": pendencias,
        "registros": [_dump_registro(db, r) for r in registros],
        "tipos": [{"id": str(t.id), "nome": t.nome, "descricao": t.descricao,
                   "critico": t.critico, "exige_validade": t.exige_validade,
                   "documentos_exigidos": t.documentos_exigidos or []}
                  for t in tipos_do_cargo(db, col.cargo_funcao)],
    }


# ---------------------------------------------------------------------------
# 3) meu desenvolvimento: criar registro, subir documento, enviar
# ---------------------------------------------------------------------------


class RegistroIn(BaseModel):
    tipo_id: uuid.UUID
    titulo: str | None = None
    instituicao: str | None = None
    carga_horaria: str | None = None
    concluido_em: str | None = None   # dd/mm/aaaa ou aaaa-mm-dd
    observacao: str | None = None


def _data_de(txt: str | None) -> date | None:
    txt = (txt or "").strip()
    if not txt:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return None


def _registro_editavel(db: Session, col: Candidato,
                       registro_id: uuid.UUID) -> RegistroDesenvolvimento:
    r = db.get(RegistroDesenvolvimento, registro_id)
    if r is None or r.candidato_id != col.id:
        raise HTTPException(status_code=404, detail="registro_nao_encontrado")
    # Validado/recusado é decisão do RH: o colaborador não reabre por conta
    # própria (para corrigir, o RH devolve — que volta para `devolvido`).
    if r.status not in (StatusRegistro.pendente, StatusRegistro.devolvido):
        raise HTTPException(status_code=409, detail="registro_fechado")
    return r


@router.post("/portal/sessao/{token}/registros", status_code=201)
def criar_registro(token: str, payload: RegistroIn,
                   db: Session = Depends(get_db)) -> dict:
    _, col = _sessao(db, token)
    tipo = db.get(TipoDesenvolvimento, payload.tipo_id)
    if tipo is None or not tipo.ativo:
        raise HTTPException(status_code=404, detail="tipo_nao_encontrado")
    concluido = _data_de(payload.concluido_em)
    r = RegistroDesenvolvimento(
        candidato_id=col.id, tipo_id=tipo.id,
        titulo=(payload.titulo or tipo.nome).strip()[:200],
        instituicao=(payload.instituicao or "").strip()[:200] or None,
        carga_horaria=(payload.carga_horaria or "").strip()[:30] or None,
        concluido_em=concluido,
        observacao=(payload.observacao or "").strip() or None,
        # A validade é proposta aqui, mas só vale depois que o RH validar — o
        # `validar` recalcula com o prazo vigente naquele momento.
        validade_ate=calcular_validade(concluido, meses_validade_de(db, tipo, col)),
        status=StatusRegistro.pendente, enviado_por="colaborador")
    db.add(r)
    registrar(db, "portal_registro_criado", ator="colaborador", candidato_id=col.id,
              detalhe={"tipo": tipo.nome})
    db.commit()
    db.refresh(r)
    return _dump_registro(db, r)


@router.put("/portal/sessao/{token}/registros/{registro_id}")
def editar_registro(token: str, registro_id: uuid.UUID, payload: RegistroIn,
                    db: Session = Depends(get_db)) -> dict:
    """Confirmação/ajuste do que a IA propôs — é aqui que o humano decide."""
    _, col = _sessao(db, token)
    r = _registro_editavel(db, col, registro_id)
    if payload.titulo is not None:
        r.titulo = payload.titulo.strip()[:200] or None
    if payload.instituicao is not None:
        r.instituicao = payload.instituicao.strip()[:200] or None
    if payload.carga_horaria is not None:
        r.carga_horaria = payload.carga_horaria.strip()[:30] or None
    if payload.observacao is not None:
        r.observacao = payload.observacao.strip() or None
    if payload.concluido_em is not None:
        r.concluido_em = _data_de(payload.concluido_em)
        r.validade_ate = calcular_validade(
            r.concluido_em, meses_validade_de(db, r.tipo, col))
    # Reenvio depois de devolvido volta para a fila do RH
    reenviado = r.status == StatusRegistro.devolvido
    if reenviado:
        r.status = StatusRegistro.pendente
    db.commit()
    db.refresh(r)
    # avisa o RH que entrou (ou voltou) algo na fila — destinatários na matriz
    from app.services.notificacoes import avisar
    avisar(db, "desenvolvimento_enviado",
           f"🎓 {col.nome_completo} enviou um documento",
           f"{col.nome_completo} {'reenviou' if reenviado else 'enviou'} "
           f"\"{r.titulo or (r.tipo.nome if r.tipo else 'um documento')}\" "
           "para validação.\nAcesse o painel do RH › Desenvolvimento.\n")
    return _dump_registro(db, r)


@router.post("/portal/sessao/{token}/registros/{registro_id}/documento")
async def subir_documento(token: str, registro_id: uuid.UUID, papel: str,
                          arquivo: UploadFile, db: Session = Depends(get_db)) -> dict:
    """Sobe um documento do registro e devolve o que a IA leu, para o
    colaborador CONFERIR — nada é gravado a partir da leitura."""
    _, col = _sessao(db, token)
    r = _registro_editavel(db, col, registro_id)
    if papel not in PAPEIS_VALIDOS:
        raise HTTPException(status_code=422, detail="papel_invalido")
    try:
        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(status_code=422, detail="arquivo_vazio")
        if len(conteudo) > TAMANHO_MAX:
            raise HTTPException(status_code=422, detail="arquivo_grande")
        ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5]
        if ext not in EXT_ACEITAS:
            raise HTTPException(status_code=422, detail="formato_nao_aceito")
    finally:
        # Starlette faz spool em disco acima de ~1MB: sem o close, o temp file
        # ficaria no container com documento pessoal dentro (regra da casa).
        await arquivo.close()

    sensibilidade = SENSIBILIDADE_PAPEL.get(papel, SensibilidadeDoc.comum)
    key = f"desenvolvimento/{r.id}/{papel}.{ext}"
    storage.salvar(key, conteudo, arquivo.content_type or "application/octet-stream")

    # substitui o documento do mesmo papel, se já havia
    for antigo in list(r.arquivos):
        if antigo.papel == papel:
            db.delete(antigo)
    db.add(ArquivoDesenvolvimento(
        registro_id=r.id, papel=papel, sensibilidade=sensibilidade, key=key,
        nome_original=(arquivo.filename or "")[:200],
        content_type=arquivo.content_type, tamanho=len(conteudo),
        sha256=hashlib.sha256(conteudo).hexdigest()))

    # Leitura assistida: propõe campos para a pessoa conferir. Documento de
    # saúde só passa se o ZDR estiver ligado (trava do `ocr_roteador`).
    from app.services.ocr_certificado import sugestoes
    from app.services.ocr_roteador import carimbar_leitura, ler_documento
    texto, motivo = ler_documento(db, conteudo, ext, sensibilidade, col.id)
    sug = sugestoes(papel, texto or "")
    carimbar_leitura(r, {**(r.extraido_ia or {}), papel: sug} if sug else r.extraido_ia)
    db.commit()
    db.refresh(r)
    return {"registro": _dump_registro(db, r), "sugestoes": sug,
            "leitura": motivo}


@router.delete("/portal/sessao/{token}/registros/{registro_id}", status_code=204)
def excluir_registro(token: str, registro_id: uuid.UUID,
                     db: Session = Depends(get_db)) -> None:
    _, col = _sessao(db, token)
    r = _registro_editavel(db, col, registro_id)
    for a in r.arquivos:
        try:
            storage.remover(a.key)
        except Exception:
            pass  # arquivo já sumiu do MinIO: seguir e apagar o registro
    db.delete(r)
    db.commit()
