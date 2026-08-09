import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_senha
from app.models.usuario_rh import UsuarioRH

log = logging.getLogger(__name__)


def criar_admin_inicial(db: Session) -> None:
    """Cria o primeiro usuário do RH a partir do .env, se a tabela estiver vazia.

    Caminho OPCIONAL desde a v2.84, para instalação automatizada (provisionamento
    sem ninguém na tela). Com as variáveis vazias — o padrão — nada acontece
    aqui, e quem cria o primeiro administrador é a tela de PRIMEIRO ACESSO
    (`/rh/auth/primeiro-acesso`): assim nenhuma senha precisa ser escrita em
    arquivo, e o e-mail de quem opera não vive no repositório.

    As duas portas dividem o MESMO portão — "a tabela está vazia" —, então elas
    não se atropelam: preenchido o `.env`, o admin nasce aqui e a tela de
    primeiro acesso já não aparece.
    """
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
