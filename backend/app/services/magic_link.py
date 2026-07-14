import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.candidato import AcessoMagico, Candidato


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def emitir_link(db: Session, candidato: Candidato, base_url: str | None = None) -> str:
    """Gera um token de acesso e retorna a URL completa a ser enviada ao candidato.
    base_url deve vir da requisição (core.config.base_url_publica); sem ela, cai
    no BASE_URL do .env."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    acesso = AcessoMagico(
        candidato_id=candidato.id,
        token_hash=_hash(token),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=settings.magic_link_ttl_hours),
    )
    db.add(acesso)
    db.flush()
    return f"{base_url or settings.base_url}/c/{token}"


def resolver_token(db: Session, token: str) -> Candidato | None:
    """Valida o token e devolve o candidato; None se inválido/expirado/revogado."""
    acesso = db.scalar(select(AcessoMagico).where(AcessoMagico.token_hash == _hash(token)))
    if acesso is None or acesso.revogado:
        return None
    if acesso.expira_em < datetime.now(timezone.utc):
        return None
    if acesso.usado_em is None:
        acesso.usado_em = datetime.now(timezone.utc)
    return db.get(Candidato, acesso.candidato_id)
