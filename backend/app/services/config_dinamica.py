"""Configuração dinâmica: valores do banco (painel) sobrepõem o .env."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.configuracao import Configuracao

CHAVES_SMTP = ("smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from")


def ler_config(db: Session, chaves: tuple[str, ...]) -> dict[str, str]:
    registros = db.scalars(select(Configuracao).where(Configuracao.chave.in_(chaves))).all()
    return {r.chave: r.valor for r in registros}


def gravar_config(db: Session, valores: dict[str, str]) -> None:
    for chave, valor in valores.items():
        registro = db.get(Configuracao, chave)
        if registro is None:
            db.add(Configuracao(chave=chave, valor=valor))
        else:
            registro.valor = valor
    db.flush()


def smtp_config(db: Session) -> dict:
    """SMTP efetivo: banco > .env."""
    s = get_settings()
    banco = ler_config(db, CHAVES_SMTP)
    return {
        "host": banco.get("smtp_host", s.smtp_host),
        "port": int(banco.get("smtp_port", s.smtp_port) or 587),
        "user": banco.get("smtp_user", s.smtp_user),
        "password": banco.get("smtp_password", s.smtp_password),
        "from_": banco.get("smtp_from", s.smtp_from),
    }
