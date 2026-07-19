"""Multi-signatário — assinatura do signatário EXTERNO (terceiro sem conta) e a
verificação pública por etapa.

Correções: C2 (token single-use; PDF/preview só após OTP validado — dados de
terceiro nunca ficam atrás só do token na URL), m10 (compare_digest no OTP),
M8 (verificação pública mostra só o assinante daquela etapa + contagem X de N,
sem lista nominal de coassinantes)."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, get_settings, ip_do_cliente
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                               SolicitacaoAssinatura,
                                               StatusSolicitacao)
from app.services.auditoria import registrar
from app.services.limite import exigir
from app.services.roteiro_assinatura import avancar_solicitacao

router = APIRouter(tags=["assinatura-externa"])

MAX_TENTATIVAS_OTP = 5


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def emitir_link_etapa(db: Session, etapa: EtapaAssinatura, base_url: str | None) -> str:
    """Gera um token novo para a etapa externa (SHA-256 guardado). O caller
    comita."""
    token = secrets.token_urlsafe(32)
    etapa.token_hash = _hash(token)
    return f"{(base_url or get_settings().base_url)}/assinar/{token}"


def _etapa_por_token(db: Session, token: str) -> EtapaAssinatura:
    e = db.scalar(select(EtapaAssinatura).where(EtapaAssinatura.token_hash == _hash(token)))
    if e is None:
        raise HTTPException(status_code=404, detail="link_invalido")
    return e


def _solicitacao_valida(db: Session, e: EtapaAssinatura) -> SolicitacaoAssinatura:
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    if sol is None or sol.status != StatusSolicitacao.aguardando:
        raise HTTPException(status_code=409, detail="documento_indisponivel")
    return sol


@router.get("/assinar/{token}")
def info_etapa(token: str, db: Session = Depends(get_db)) -> dict:
    """Metadados mínimos (sem o PDF, que exige o 2º fator — correção C2)."""
    e = _etapa_por_token(db, token)
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    na_vez = (sol.status == StatusSolicitacao.aguardando
              and e.ordem == sol.etapa_atual_ordem and e.assinado_em is None)
    return {
        "titulo": sol.titulo_doc or sol.documento, "papel": e.papel,
        "nome": e.externo_nome, "na_vez": na_vez,
        "ja_assinou": e.assinado_em is not None,
        "recusada": e.recusada_em is not None,
        "documento_disponivel": sol.status == StatusSolicitacao.aguardando,
        "otp_validado": e.otp_validado_em is not None,
    }


@router.post("/assinar/{token}/solicitar-codigo", status_code=204)
def solicitar_codigo_externo(token: str, request: Request,
                             db: Session = Depends(get_db)) -> None:
    exigir(f"assin-ext-cod:{token[:16]}", maximo=5, janela_s=900)
    e = _etapa_por_token(db, token)
    sol = _solicitacao_valida(db, e)
    if e.assinado_em is not None:
        raise HTTPException(status_code=409, detail="ja_assinou")
    if e.ordem != sol.etapa_atual_ordem:
        raise HTTPException(status_code=409, detail="fora_da_vez")
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    e.otp_hash = _hash(codigo)
    e.otp_expira_em = datetime.now(timezone.utc) + timedelta(
        minutes=get_settings().otp_ttl_minutes)
    e.otp_tentativas = 0
    db.commit()
    from app.services.email import enviar_email, html_moderno
    enviar_email(
        e.externo_email,
        "Green House — código para assinar o documento",
        f"Seu código de assinatura é: {codigo}\n\n"
        f"Ele vale por {get_settings().otp_ttl_minutes} minutos.\n",
        html_moderno("Seu código de assinatura", [
            f"Olá, <strong>{e.externo_nome}</strong>!",
            "Use o código abaixo para confirmar e assinar o documento:",
            f"<div style='font-size:2rem;font-weight:800;letter-spacing:.3em;"
            f"text-align:center;margin:1rem 0;color:#0a8f46'>{codigo}</div>"]))


class ConfirmarIn(BaseModel):
    codigo: str


@router.post("/assinar/{token}/confirmar")
def confirmar_codigo_externo(token: str, payload: ConfirmarIn,
                             db: Session = Depends(get_db)) -> dict:
    """Valida o OTP e abre a sessão curta que libera ver o PDF e assinar."""
    exigir(f"assin-ext-conf:{token[:16]}", maximo=10, janela_s=900)
    e = _etapa_por_token(db, token)
    _solicitacao_valida(db, e)
    if e.otp_hash is None or e.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if e.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if e.otp_tentativas >= MAX_TENTATIVAS_OTP:
        raise HTTPException(status_code=429, detail="tentativas_excedidas")
    if not secrets.compare_digest(_hash(payload.codigo.strip()), e.otp_hash):
        e.otp_tentativas += 1
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_incorreto")
    e.otp_validado_em = datetime.now(timezone.utc)
    db.commit()
    return {"validado": True}


def _exigir_otp_validado(e: EtapaAssinatura) -> None:
    # C2: PDF/assinatura só depois do 2º fator, dentro de uma janela curta
    if e.otp_validado_em is None:
        raise HTTPException(status_code=403, detail="confirme_o_codigo_primeiro")
    if e.otp_validado_em < datetime.now(timezone.utc) - timedelta(minutes=30):
        raise HTTPException(status_code=403, detail="sessao_expirada")


@router.get("/assinar/{token}/preview")
def preview_externo(token: str, db: Session = Depends(get_db)) -> Response:
    """PDF do documento — só após o OTP validado (dados de terceiro protegidos)."""
    e = _etapa_por_token(db, token)
    sol = _solicitacao_valida(db, e)
    _exigir_otp_validado(e)
    cand = db.get(Candidato, sol.candidato_id)
    from app.services.fichas import gerar_documento_modelo
    pdf = gerar_documento_modelo(db, sol.titulo_doc or "Documento", sol.corpo_doc or "", cand)
    return Response(content=pdf, media_type="application/pdf")


@router.post("/assinar/{token}/assinar")
def assinar_externo(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    e = _etapa_por_token(db, token)
    sol = _solicitacao_valida(db, e)
    _exigir_otp_validado(e)
    if e.assinado_em is not None:
        raise HTTPException(status_code=409, detail="ja_assinou")
    if e.ordem != sol.etapa_atual_ordem:
        raise HTTPException(status_code=409, detail="fora_da_vez")
    agora = datetime.now(timezone.utc)
    e.assinado_em = agora
    e.assinante_nome = e.externo_nome
    e.assinante_cpf = (f"{e.externo_cpf[:3]}.{e.externo_cpf[3:6]}.{e.externo_cpf[6:9]}-{e.externo_cpf[9:]}"
                       if e.externo_cpf and len(e.externo_cpf) == 11 else None)
    e.ip = ip_do_cliente(request)
    e.user_agent = request.headers.get("user-agent", "")[:400]
    e.prova_metodo = "otp_email"
    e.hash_sha256 = _hash(f"{sol.id}:{e.id}:{e.externo_email}:{agora.isoformat()}")
    # C2: token single-use — some após concluir
    e.token_hash = None
    e.otp_hash = None
    registrar(db, "etapa_assinada", ator="externo", candidato_id=sol.candidato_id,
              detalhe={"papel": e.papel, "metodo": "otp_email"})
    db.commit()
    resultado = avancar_solicitacao(db, sol.id)
    db.commit()
    from app.api.solicitacoes_assinatura import _notificar_liberadas
    _notificar_liberadas(db, sol, resultado["notificar"], base_url_publica(request))
    return {"assinado": True, "concluida": resultado["concluida"]}


# ---------------------------------------------------------------------------
# Verificação pública por etapa (M8: só o assinante daquela etapa + X de N)
# ---------------------------------------------------------------------------


@router.get("/verificar-etapa/{etapa_id}")
def verificar_etapa(etapa_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    from app.api.assinaturas import _cpf_mascarado, _nome_mascarado
    e = db.get(EtapaAssinatura, etapa_id)
    if e is None or e.assinado_em is None:
        raise HTTPException(status_code=404, detail="assinatura_nao_encontrada")
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    etapas = db.scalars(select(EtapaAssinatura)
                        .where(EtapaAssinatura.solicitacao_id == sol.id)).all()
    assinadas = sum(1 for x in etapas if x.assinado_em is not None)
    registrar(db, "etapa_verificada", ator="publico", candidato_id=sol.candidato_id,
              detalhe={"etapa": str(e.id)})
    db.commit()
    return {
        "valida": True,
        "documento": sol.titulo_doc or sol.documento,
        # M8: só o assinante DESTA etapa (nada de listar os coassinantes)
        "assinante": _nome_mascarado(e.assinante_nome or "-"),
        "papel": e.papel,
        "cpf": _cpf_mascarado(e.assinante_cpf),
        "assinado_em": e.assinado_em,
        "hash_sha256": e.hash_sha256,
        "assinaturas_no_documento": f"{assinadas} de {len(etapas)}",
        "documento_concluido": sol.status == StatusSolicitacao.concluida,
    }
