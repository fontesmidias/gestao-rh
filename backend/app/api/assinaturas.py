"""Assinatura eletrônica simples das 3 fichas: preview → OTP → assinar."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.assinatura import Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, StatusCandidato
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email
from app.services.fichas import GERADORES
from app.services.magic_link import resolver_token

router = APIRouter(tags=["assinaturas"])

MAX_TENTATIVAS_OTP = 5


def _candidato_do_token(token: str, db: Session) -> Candidato:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    return candidato


def _registro(db: Session, candidato: Candidato, documento: DocumentoAssinavel) -> Assinatura:
    assinatura = db.scalar(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id, Assinatura.documento == documento
        )
    )
    if assinatura is None:
        assinatura = Assinatura(candidato_id=candidato.id, documento=documento)
        db.add(assinatura)
        db.flush()
    return assinatura


@router.get("/c/{token}/fichas")
def status_fichas(token: str, db: Session = Depends(get_db)) -> dict:
    candidato = _candidato_do_token(token, db)
    assinaturas = db.scalars(
        select(Assinatura).where(Assinatura.candidato_id == candidato.id)
    ).all()
    por_doc = {a.documento: a for a in assinaturas}
    db.commit()
    return {
        "fichas": [
            {
                "documento": doc,
                "assinado": doc in por_doc and por_doc[doc].assinado_em is not None,
                "assinado_em": por_doc[doc].assinado_em if doc in por_doc else None,
            }
            for doc in DocumentoAssinavel
        ]
    }


@router.get("/c/{token}/fichas/{documento}/preview")
def preview(token: str, documento: DocumentoAssinavel, db: Session = Depends(get_db)) -> Response:
    """PDF gerado com os dados atuais, ainda sem valor de assinatura."""
    candidato = _candidato_do_token(token, db)
    pdf = GERADORES[documento.value](db, candidato)
    db.commit()
    return Response(content=pdf, media_type="application/pdf")


@router.post("/c/{token}/fichas/{documento}/solicitar-codigo", status_code=204)
def solicitar_codigo(
    token: str, documento: DocumentoAssinavel, db: Session = Depends(get_db)
) -> None:
    candidato = _candidato_do_token(token, db)
    if candidato.status not in (StatusCandidato.aguardando_assinatura,
                                StatusCandidato.docs_pendentes,
                                StatusCandidato.preenchendo):
        raise HTTPException(status_code=409, detail="fase_invalida_para_assinatura")
    assinatura = _registro(db, candidato, documento)
    if assinatura.assinado_em is not None:
        raise HTTPException(status_code=409, detail="documento_ja_assinado")

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    assinatura.otp_hash = hashlib.sha256(codigo.encode()).hexdigest()
    assinatura.otp_expira_em = datetime.now(timezone.utc) + timedelta(
        minutes=get_settings().otp_ttl_minutes
    )
    assinatura.otp_tentativas = 0
    db.commit()

    nome_doc = documento.value.replace("_", " ").title()
    enviar_email(
        candidato.email,
        f"🌱 Green House — seu código para assinar: {nome_doc}",
        f"Seu código de assinatura é: {codigo}\n\n"
        f"Ele vale por {get_settings().otp_ttl_minutes} minutos e serve apenas para o "
        f"documento '{nome_doc}'. Se você não pediu este código, ignore este e-mail.\n",
    )


class AssinarIn(BaseModel):
    codigo: str


@router.post("/c/{token}/fichas/{documento}/assinar")
def assinar(
    token: str,
    documento: DocumentoAssinavel,
    payload: AssinarIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    candidato = _candidato_do_token(token, db)
    assinatura = _registro(db, candidato, documento)
    if assinatura.assinado_em is not None:
        raise HTTPException(status_code=409, detail="documento_ja_assinado")
    if assinatura.otp_hash is None or assinatura.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if assinatura.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if assinatura.otp_tentativas >= MAX_TENTATIVAS_OTP:
        raise HTTPException(status_code=429, detail="tentativas_excedidas")

    if hashlib.sha256(payload.codigo.encode()).hexdigest() != assinatura.otp_hash:
        assinatura.otp_tentativas += 1
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_incorreto")

    # Evidências: hash do documento SEM o bloco de assinatura, IP, user-agent, instante.
    pdf_sem_bloco = GERADORES[documento.value](db, candidato)
    assinatura.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
    assinatura.assinado_em = datetime.now(timezone.utc)
    assinatura.ip = request.client.host if request.client else None
    assinatura.user_agent = request.headers.get("user-agent", "")[:400]
    assinatura.otp_hash = None
    assinatura.otp_expira_em = None

    pdf_assinado = GERADORES[documento.value](db, candidato, assinatura)
    key = f"candidatos/{candidato.id}/fichas/{documento.value}.pdf"
    storage.salvar(key, pdf_assinado, "application/pdf")
    assinatura.pdf_key = key

    # Assinou as 3? Candidato segue para a etapa de documentos.
    assinadas = db.scalars(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id, Assinatura.assinado_em.isnot(None)
        )
    ).all()
    todas = {a.documento for a in assinadas} | {documento}
    if todas == set(DocumentoAssinavel) and candidato.status == StatusCandidato.aguardando_assinatura:
        candidato.status = StatusCandidato.docs_pendentes

    registrar(db, "documento_assinado", ator="candidato", candidato_id=candidato.id,
              detalhe={"documento": documento.value, "hash": assinatura.hash_sha256})
    db.commit()
    return {
        "documento": documento,
        "assinado_em": assinatura.assinado_em,
        "hash_sha256": assinatura.hash_sha256,
    }
