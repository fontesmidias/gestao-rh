import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_senha
from app.models.usuario_rh import UsuarioRH

log = logging.getLogger(__name__)


def criar_admin_inicial(db: Session) -> None:
    """Cria o primeiro usuário do RH a partir do .env, apenas se a tabela estiver vazia."""
    settings = get_settings()
    if not settings.rh_admin_email or not settings.rh_admin_password:
        return
    if db.scalar(select(UsuarioRH).limit(1)) is not None:
        return
    db.add(
        UsuarioRH(
            nome="Administrador RH",
            email=settings.rh_admin_email.lower(),
            senha_hash=hash_senha(settings.rh_admin_password),
        )
    )
    db.commit()
    log.info("Usuário admin inicial do RH criado: %s", settings.rh_admin_email)
