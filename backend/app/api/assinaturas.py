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
    """PDF do documento: a via assinada, se existir; senão, prévia com os dados atuais."""
    candidato = _candidato_do_token(token, db)
    assinatura = db.scalar(
        select(Assinatura).where(
            Assinatura.candidato_id == candidato.id, Assinatura.documento == documento,
            Assinatura.assinado_em.isnot(None),
        )
    )
    if assinatura is not None and assinatura.pdf_key:
        pdf = storage.ler(assinatura.pdf_key)
    else:
        pdf = GERADORES[documento.value](db, candidato)
    db.commit()
    return Response(content=pdf, media_type="application/pdf")


NOMES_DOC = {
    DocumentoAssinavel.ficha_cadastro: "Ficha Cadastral do Colaborador",
    DocumentoAssinavel.ficha_emergencia: "Ficha de Emergência do Colaborador",
    DocumentoAssinavel.termo_vt: "Termo de Opção pelo Vale-Transporte",
}


@router.post("/c/{token}/fichas/solicitar-codigo", status_code=204)
def solicitar_codigo_unico(token: str, db: Session = Depends(get_db)) -> None:
    """Um único código para assinar todos os documentos pendentes de uma vez."""
    candidato = _candidato_do_token(token, db)
    pendentes = [
        d for d in DocumentoAssinavel
        if _registro(db, candidato, d).assinado_em is None
    ]
    if not pendentes:
        raise HTTPException(status_code=409, detail="todos_ja_assinados")

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    otp_hash = hashlib.sha256(codigo.encode()).hexdigest()
    expira = datetime.now(timezone.utc) + timedelta(minutes=get_settings().otp_ttl_minutes)
    for doc in pendentes:
        assinatura = _registro(db, candidato, doc)
        assinatura.otp_hash = otp_hash
        assinatura.otp_expira_em = expira
        assinatura.otp_tentativas = 0
    db.commit()

    docs = "\n".join(f"  - {NOMES_DOC[d]}" for d in pendentes)
    enviar_email(
        candidato.email,
        "Green House — Código de assinatura dos documentos admissionais",
        f"Prezado(a) {candidato.nome_completo},\n\n"
        f"Seu código de assinatura eletrônica é: {codigo}\n\n"
        f"Ele é válido por {get_settings().otp_ttl_minutes} minutos e assina, de uma só vez, "
        f"os seguintes documentos:\n{docs}\n\n"
        "Digite o código na tela de assinatura para concluir. Caso não localize esta "
        "mensagem, verifique a caixa de spam ou lixo eletrônico.\n\n"
        "Se você não solicitou este código, desconsidere esta mensagem.\n\n"
        "Atenciosamente,\nRH — Green House\n",
    )


class AssinarTodosIn(BaseModel):
    codigo: str


@router.post("/c/{token}/fichas/assinar")
def assinar_todos(
    token: str,
    payload: AssinarTodosIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Valida o código único e assina todos os documentos pendentes."""
    candidato = _candidato_do_token(token, db)
    pendentes = [
        (d, _registro(db, candidato, d)) for d in DocumentoAssinavel
        if _registro(db, candidato, d).assinado_em is None
    ]
    if not pendentes:
        raise HTTPException(status_code=409, detail="todos_ja_assinados")

    ref = pendentes[0][1]
    if ref.otp_hash is None or ref.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if ref.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if ref.otp_tentativas >= MAX_TENTATIVAS_OTP:
        raise HTTPException(status_code=429, detail="tentativas_excedidas")
    if hashlib.sha256(payload.codigo.encode()).hexdigest() != ref.otp_hash:
        for _, a in pendentes:
            a.otp_tentativas += 1
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_incorreto")

    agora = datetime.now(timezone.utc)
    anexos: list[tuple[str, bytes]] = []
    assinados = []
    for doc, assinatura in pendentes:
        pdf_sem_bloco = GERADORES[doc.value](db, candidato)
        assinatura.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
        assinatura.assinado_em = agora
        assinatura.ip = request.client.host if request.client else None
        assinatura.user_agent = request.headers.get("user-agent", "")[:400]
        assinatura.otp_hash = None
        assinatura.otp_expira_em = None
        pdf_assinado = GERADORES[doc.value](db, candidato, assinatura)
        key = f"candidatos/{candidato.id}/fichas/{doc.value}.pdf"
        storage.salvar(key, pdf_assinado, "application/pdf")
        assinatura.pdf_key = key
        anexos.append((f"{doc.value}.pdf", pdf_assinado))
        assinados.append({"documento": doc, "assinado_em": agora,
                          "hash_sha256": assinatura.hash_sha256})
        registrar(db, "documento_assinado", ator="candidato", candidato_id=candidato.id,
                  detalhe={"documento": doc.value, "hash": assinatura.hash_sha256})

    if candidato.status == StatusCandidato.aguardando_assinatura:
        candidato.status = StatusCandidato.docs_pendentes
    db.commit()

    enviar_email(
        candidato.email,
        "Green House — Seus documentos assinados (vias do colaborador)",
        f"Prezado(a) {candidato.nome_completo},\n\n"
        "Confirmamos a assinatura eletrônica dos seus documentos admissionais, que seguem "
        "anexos a esta mensagem para sua guarda:\n"
        + "\n".join(f"  - {NOMES_DOC[d]}" for d, _ in pendentes)
        + "\n\nPróximo passo obrigatório: envie a sua documentação pelo mesmo link da "
        "admissão. Sua contratação somente será efetivada após o envio completo.\n\n"
        "Atenciosamente,\nRH — Green House\n",
        anexos=anexos,
    )
    return {"assinados": assinados}


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
