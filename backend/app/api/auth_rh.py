import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica
from app.core.db import get_db
from app.core.security import (criar_token_reset, criar_token_sessao, hash_senha,
                               validar_token_reset, validar_token_sessao, verificar_senha)
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.models.usuario_rh import UsuarioRH

router = APIRouter(tags=["auth-rh"])

_bearer = HTTPBearer(auto_error=False)


class LoginIn(BaseModel):
    email: EmailStr
    senha: str


class LoginOut(BaseModel):
    token: str
    nome: str


@router.post("/rh/auth/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    usuario = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
    if usuario is None or not usuario.ativo or not verificar_senha(payload.senha, usuario.senha_hash):
        registrar(db, "login_falhou", ator="rh", ator_detalhe=payload.email)
        db.commit()
        # Mensagem única: não revelar se o e-mail existe.
        raise HTTPException(status_code=401, detail="credenciais_invalidas")
    registrar(db, "login_ok", ator="rh", ator_detalhe=usuario.email)
    db.commit()
    return LoginOut(token=criar_token_sessao(str(usuario.id)), nome=usuario.nome)


class EsqueciSenhaIn(BaseModel):
    email: EmailStr


@router.post("/rh/auth/esqueci-senha", status_code=204)
def esqueci_senha(payload: EsqueciSenhaIn, request: Request,
                  db: Session = Depends(get_db)) -> None:
    """Sempre responde 204 (não revela se o e-mail existe). Se existir e estiver
    ativo, envia link de redefinição válido por 30 minutos."""
    usuario = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
    registrar(db, "reset_senha_solicitado", ator="rh", ator_detalhe=payload.email.lower())
    db.commit()
    if usuario is None or not usuario.ativo:
        return
    token = criar_token_reset(str(usuario.id), usuario.senha_hash)
    link = f"{base_url_publica(request)}/rh?redefinir={token}"
    try:
        enviar_email(
            usuario.email,
            "🔐 Green House — redefinição de senha do painel",
            f"Olá, {usuario.nome.split()[0].title()}!\n\n"
            "Recebemos um pedido para redefinir a sua senha do painel do RH.\n"
            f"Acesse o link abaixo em ATÉ 30 MINUTOS para criar uma nova senha:\n{link}\n\n"
            "Se não foi você, ignore esta mensagem — sua senha continua a mesma.\n",
            html_moderno(
                "Redefinição de senha",
                [
                    f"Olá, <strong>{usuario.nome.split()[0].title()}</strong>!",
                    "Recebemos um pedido para redefinir a sua senha do painel do RH "
                    "do Portal de Admissão.",
                    f"<a href='{link}' style='display:inline-block;padding:12px 22px;"
                    "background:#2f7d3a;color:#fff;border-radius:10px;text-decoration:none;"
                    "font-weight:600'>Criar nova senha</a>",
                    "O link vale por <strong>30 minutos</strong> e só pode ser usado "
                    "uma vez. Se não foi você quem pediu, ignore esta mensagem — "
                    "sua senha continua a mesma.",
                ],
            ),
            levantar_erro=True,
        )
    except Exception:
        # Não propaga o erro para não revelar se o e-mail existe; fica na auditoria.
        registrar(db, "reset_senha_email_falhou", ator="sistema", ator_detalhe=usuario.email)
        db.commit()


class RedefinirSenhaIn(BaseModel):
    token: str
    senha_nova: str


@router.post("/rh/auth/redefinir-senha", status_code=204)
def redefinir_senha(payload: RedefinirSenhaIn, db: Session = Depends(get_db)) -> None:
    dados = validar_token_reset(payload.token)
    if dados is None:
        raise HTTPException(status_code=422, detail="link_invalido_ou_expirado")
    usuario = db.get(UsuarioRH, uuid.UUID(dados["sub"]))
    # O fragmento do hash garante uso único: após a troca, o token antigo morre.
    if usuario is None or not usuario.ativo or usuario.senha_hash[-16:] != dados["h"]:
        raise HTTPException(status_code=422, detail="link_invalido_ou_expirado")
    if len(payload.senha_nova) < 8:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")
    usuario.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "senha_redefinida_por_link", ator="rh", ator_detalhe=usuario.email)
    db.commit()


def requer_rh(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> UsuarioRH:
    """Dependência para proteger endpoints /rh/*."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="nao_autenticado")
    usuario_id = validar_token_sessao(credentials.credentials)
    if usuario_id is None:
        raise HTTPException(status_code=401, detail="sessao_invalida_ou_expirada")
    usuario = db.get(UsuarioRH, uuid.UUID(usuario_id))
    if usuario is None or not usuario.ativo:
        raise HTTPException(status_code=401, detail="usuario_inativo")
    return usuario
