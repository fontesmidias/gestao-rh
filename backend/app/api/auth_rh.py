import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import criar_token_sessao, validar_token_sessao, verificar_senha
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
        # Mensagem única: não revelar se o e-mail existe.
        raise HTTPException(status_code=401, detail="credenciais_invalidas")
    return LoginOut(token=criar_token_sessao(str(usuario.id)), nome=usuario.nome)


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
