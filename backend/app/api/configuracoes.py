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


# ---------- Microsoft 365 (OAuth + Graph) ----------

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings
from app.services import m365
from app.services.config_dinamica import gravar_config


def _state_serializer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt="m365-oauth")


def _redirect_uri() -> str:
    return f"{get_settings().base_url}/api/rh/config/m365/callback"


class M365In(BaseModel):
    client_id: str
    tenant_id: str
    client_secret: str | None = None  # None = manter


@router.get("/rh/config/m365")
def ver_m365(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cfg = m365.config_m365(db)
    return {
        "client_id": cfg.get("m365_client_id", ""),
        "tenant_id": cfg.get("m365_tenant_id", ""),
        "secret_definido": bool(cfg.get("m365_client_secret")),
        "conectado": bool(cfg.get("m365_refresh_token")),
        "conta": cfg.get("m365_conta", ""),
        "redirect_uri": _redirect_uri(),
    }


@router.put("/rh/config/m365")
def salvar_m365(payload: M365In, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    valores = {"m365_client_id": payload.client_id.strip(),
               "m365_tenant_id": payload.tenant_id.strip()}
    if payload.client_secret:
        valores["m365_client_secret"] = payload.client_secret.strip()
    gravar_config(db, valores)
    registrar(db, "m365_config_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_m365(db, rh)


@router.get("/rh/config/m365/url-login")
def m365_url_login(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """URL de autorização com state assinado — o front abre em popup."""
    cfg = m365.config_m365(db)
    if not cfg.get("m365_client_id"):
        raise HTTPException(status_code=422, detail="configure_client_id_primeiro")
    state = _state_serializer().dumps({"rh": str(rh.id)})
    return {"url": m365.url_autorizacao(db, _redirect_uri(), state)}


@router.get("/rh/config/m365/callback")
def m365_callback(request: Request, db: Session = Depends(get_db)):
    """Retorno do login Microsoft (sem bearer: valida o state assinado)."""
    state = request.query_params.get("state", "")
    try:
        _state_serializer().loads(state, max_age=600)
    except BadSignature:
        return HTMLResponse("<h3>Sessão de conexão inválida ou expirada. Tente de novo.</h3>",
                            status_code=400)
    erro = request.query_params.get("error")
    if erro:
        desc = request.query_params.get("error_description", "")
        return HTMLResponse(f"<h3>Microsoft recusou: {erro}</h3><p>{desc}</p>", status_code=400)
    codigo = request.query_params.get("code", "")
    try:
        conta = m365.trocar_codigo(db, codigo, _redirect_uri())
    except Exception as exc:
        return HTMLResponse(f"<h3>Falha ao concluir a conexão.</h3><p>{exc}</p>", status_code=400)
    registrar(db, "m365_conectado", ator="rh", detalhe={"conta": conta})
    db.commit()
    return HTMLResponse(
        f"<div style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
        f"<h2>✅ Conta conectada: {conta}</h2>"
        f"<p>Pode fechar esta janela e voltar ao painel.</p>"
        f"<script>setTimeout(()=>window.close(),2500)</script></div>"
    )


@router.post("/rh/config/m365/desconectar", status_code=204)
def m365_desconectar(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> None:
    m365.desconectar(db)
    registrar(db, "m365_desconectado", ator="rh", ator_detalhe=rh.email)
    db.commit()


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
