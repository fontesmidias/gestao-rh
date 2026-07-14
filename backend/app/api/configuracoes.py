"""Configurações pelo painel: perfil do usuário do RH e SMTP (com teste de envio)."""

import smtplib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.core.security import hash_senha, verificar_senha
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.config_dinamica import CHAVES_SMTP, gravar_config, smtp_config
from app.services.email import enviar_email

router = APIRouter(tags=["configuracoes"])


# ---------- Perfil ----------


class PerfilIn(BaseModel):
    nome: str | None = None
    email: EmailStr | None = None


@router.get("/rh/me")
def meu_perfil(rh: UsuarioRH = Depends(requer_rh)) -> dict:
    return {"nome": rh.nome, "email": rh.email}


@router.put("/rh/me")
def atualizar_perfil(payload: PerfilIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if payload.email and payload.email.lower() != rh.email:
        existe = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
        if existe is not None:
            raise HTTPException(status_code=409, detail="email_ja_utilizado")
        rh.email = payload.email.lower()
    if payload.nome:
        rh.nome = payload.nome
    registrar(db, "perfil_atualizado", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"nome": rh.nome, "email": rh.email}


class SenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str


@router.put("/rh/me/senha", status_code=204)
def trocar_senha(payload: SenhaIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    if not verificar_senha(payload.senha_atual, rh.senha_hash):
        raise HTTPException(status_code=422, detail="senha_atual_incorreta")
    if len(payload.senha_nova) < 8:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")
    rh.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "senha_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ---------- SMTP ----------


class SmtpIn(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str | None = None  # None = manter a senha atual
    smtp_from: EmailStr


@router.get("/rh/config/smtp")
def ver_smtp(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cfg = smtp_config(db)
    return {
        "smtp_host": cfg["host"], "smtp_port": cfg["port"], "smtp_user": cfg["user"],
        "smtp_from": cfg["from_"], "senha_definida": bool(cfg["password"]),
    }


@router.put("/rh/config/smtp")
def salvar_smtp(payload: SmtpIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    valores = {
        "smtp_host": payload.smtp_host.strip(),
        "smtp_port": str(payload.smtp_port),
        "smtp_user": payload.smtp_user.strip(),
        "smtp_from": str(payload.smtp_from),
    }
    if payload.smtp_password:
        valores["smtp_password"] = payload.smtp_password
    gravar_config(db, valores)
    registrar(db, "smtp_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"host": valores["smtp_host"], "user": valores["smtp_user"]})
    db.commit()
    return ver_smtp(db, rh)


@router.post("/rh/config/smtp/testar")
def testar_smtp(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    try:
        enviar_email(
            rh.email, "✅ Teste de e-mail — Portal de Admissão Green House",
            "Se você recebeu esta mensagem, o SMTP do Portal de Admissão está funcionando.",
            levantar_erro=True,
        )
    except RuntimeError:
        raise HTTPException(status_code=422, detail="smtp_nao_configurado")
    except smtplib.SMTPAuthenticationError as exc:
        raise HTTPException(
            status_code=422,
            detail="autenticacao_recusada: verifique usuário/senha. No Microsoft 365, o "
                   "'SMTP AUTH' precisa estar habilitado para a caixa (Exchange admin) e, com "
                   "MFA, use uma senha de aplicativo.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"falha_no_envio: {exc}") from exc
    registrar(db, "smtp_teste_ok", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"enviado_para": rh.email}


# ---------- Auditoria ----------


@router.get("/rh/auditoria")
def auditoria(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh),
              limite: int = 200) -> list[dict]:
    from app.models.evento import EventoAuditoria

    eventos = db.scalars(
        select(EventoAuditoria).order_by(EventoAuditoria.criado_em.desc()).limit(min(limite, 500))
    ).all()
    return [
        {"quando": e.criado_em, "acao": e.acao, "ator": e.ator, "ator_detalhe": e.ator_detalhe,
         "candidato_id": e.candidato_id, "detalhe": e.detalhe}
        for e in eventos
    ]
