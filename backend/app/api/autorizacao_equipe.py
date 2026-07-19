"""Assinatura da equipe SEM correr atrás do representante a cada documento —
feita como AUTORIZAÇÃO PRÉVIA REGISTRADA, não como PNG chumbado (decisão da
revisão em party-mode, 2026-07-19).

O representante confirma UMA vez, por código no e-mail (ato de vontade real e
datado), autorizando que sua assinatura conste nos documentos gerados a partir
de um modelo, por um período. Quando um roteiro daquele modelo é montado, uma
etapa desse papel entra já satisfeita pela autorização — e o documento diz
'emitido sob autorização permanente de X, ato N, data', NUNCA 'X assinou agora'.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import get_settings, ip_do_cliente
from app.core.db import get_db
from app.models.modelo_documento import ModeloDocumento
from app.models.solicitacao_assinatura import AutorizacaoEquipe
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.limite import exigir

router = APIRouter(tags=["autorizacao-equipe"])


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def _dump(a: AutorizacaoEquipe) -> dict:
    return {
        "id": a.id, "modelo_id": a.modelo_id, "nome": a.nome, "cargo": a.cargo,
        "email": a.email, "papel": a.papel,
        "autorizado_em": a.autorizado_em, "validade_ate": a.validade_ate,
        "revogada_em": a.revogada_em,
        "ativa": (a.autorizado_em is not None and a.revogada_em is None
                  and (a.validade_ate is None or a.validade_ate > datetime.now(timezone.utc))),
    }


class NovaAutorizacaoIn(BaseModel):
    modelo_id: uuid.UUID
    nome: str
    cargo: str | None = None
    cpf: str | None = None
    email: str
    papel: str = "Contratante"
    validade_ate: datetime | None = None


@router.get("/rh/modelos/{modelo_id}/autorizacoes-equipe",
            dependencies=[Depends(requer_rh)])
def listar(modelo_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    autos = db.scalars(select(AutorizacaoEquipe)
                       .where(AutorizacaoEquipe.modelo_id == modelo_id)
                       .order_by(AutorizacaoEquipe.criado_em.desc())).all()
    return {"autorizacoes": [_dump(a) for a in autos]}


@router.post("/rh/autorizacoes-equipe", status_code=201,
             dependencies=[Depends(requer_rh)])
def criar(payload: NovaAutorizacaoIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Cadastra a autorização e dispara o código de confirmação ao representante
    (a autorização só vale DEPOIS que ele confirma — é o ato de vontade dele)."""
    if db.get(ModeloDocumento, payload.modelo_id) is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    if "@" not in payload.email:
        raise HTTPException(status_code=422, detail="email_invalido")
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    a = AutorizacaoEquipe(
        modelo_id=payload.modelo_id, nome=payload.nome.strip()[:120],
        cargo=(payload.cargo or "").strip()[:120] or None,
        cpf="".join(c for c in (payload.cpf or "") if c.isdigit())[:11] or None,
        email=payload.email.strip()[:180], papel=payload.papel.strip()[:60] or "Contratante",
        validade_ate=payload.validade_ate, criado_por=rh.email,
        otp_hash=_hash(codigo),
        otp_expira_em=datetime.now(timezone.utc) + timedelta(minutes=get_settings().otp_ttl_minutes))
    db.add(a)
    registrar(db, "autorizacao_equipe_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": a.nome, "modelo": str(payload.modelo_id)})
    db.commit()
    from app.services.email import enviar_email, html_moderno
    enviar_email(
        a.email,
        "Green House — confirme sua autorização de assinatura",
        f"Olá, {a.nome}!\n\nO RH da Green House registrou uma autorização para que a "
        f"sua assinatura, na qualidade de {a.papel}, conste nos documentos gerados a "
        f"partir de um modelo.\n\nPara CONFIRMAR esta autorização (ato de vontade), use "
        f"o código: {codigo}\n\nEle vale por {get_settings().otp_ttl_minutes} minutos. "
        "Se você não reconhece este pedido, ignore este e-mail.\n",
        html_moderno("Confirme sua autorização de assinatura", [
            f"Olá, <strong>{a.nome}</strong>!",
            f"O RH registrou uma autorização para que a sua assinatura, na qualidade de "
            f"<strong>{a.papel}</strong>, conste nos documentos gerados a partir de um "
            "modelo. Confirme com o código abaixo:",
            f"<div style='font-size:2rem;font-weight:800;letter-spacing:.3em;"
            f"text-align:center;margin:1rem 0;color:#0a8f46'>{codigo}</div>",
            "Se você não reconhece este pedido, ignore este e-mail."]))
    return _dump(a)


class ConfirmarIn(BaseModel):
    autorizacao_id: uuid.UUID
    codigo: str


@router.post("/rh/autorizacoes-equipe/confirmar", dependencies=[Depends(requer_rh)])
def confirmar(payload: ConfirmarIn, request: Request, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """O RH digita o código que o representante recebeu (ou o próprio
    representante o informa). Valida e ATIVA a autorização."""
    exigir(f"auth-equipe:{payload.autorizacao_id}", maximo=10, janela_s=900)
    a = db.get(AutorizacaoEquipe, payload.autorizacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="autorizacao_nao_encontrada")
    if a.otp_hash is None or a.otp_expira_em is None:
        raise HTTPException(status_code=409, detail="codigo_nao_solicitado")
    if a.otp_expira_em < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="codigo_expirado")
    if not secrets.compare_digest(_hash(payload.codigo.strip()), a.otp_hash):
        raise HTTPException(status_code=422, detail="codigo_incorreto")
    agora = datetime.now(timezone.utc)
    a.autorizado_em = agora
    a.ip = ip_do_cliente(request)
    a.hash_sha256 = _hash(f"{a.id}:{a.email}:{agora.isoformat()}")
    a.otp_hash = None
    registrar(db, "autorizacao_equipe_confirmada", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": a.nome, "hash": a.hash_sha256})
    db.commit()
    return _dump(a)


@router.post("/rh/autorizacoes-equipe/{aut_id}/revogar",
             dependencies=[Depends(requer_rh)])
def revogar(aut_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    a = db.get(AutorizacaoEquipe, aut_id)
    if a is None:
        raise HTTPException(status_code=404, detail="autorizacao_nao_encontrada")
    a.revogada_em = datetime.now(timezone.utc)
    registrar(db, "autorizacao_equipe_revogada", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": a.nome})
    db.commit()
    return _dump(a)


def autorizacoes_ativas(db: Session, modelo_id: uuid.UUID) -> list[AutorizacaoEquipe]:
    """Autorizações ATIVAS de um modelo — usadas para injetar etapas já
    satisfeitas ao montar um roteiro daquele modelo."""
    agora = datetime.now(timezone.utc)
    autos = db.scalars(select(AutorizacaoEquipe)
                       .where(AutorizacaoEquipe.modelo_id == modelo_id,
                              AutorizacaoEquipe.autorizado_em.isnot(None),
                              AutorizacaoEquipe.revogada_em.is_(None))).all()
    return [a for a in autos if a.validade_ate is None or a.validade_ate > agora]
