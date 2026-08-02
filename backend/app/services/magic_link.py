import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.candidato import AcessoMagico, Candidato


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def emitir_link(db: Session, candidato: Candidato, base_url: str | None = None,
                assistido_por: str | None = None,
                horas: int | None = None) -> str:
    """Gera um token de acesso e retorna a URL completa a ser enviada ao candidato.

    base_url deve vir da requisição (core.config.base_url_publica); sem ela, cai
    no BASE_URL do .env.

    `assistido_por` marca o link como sessão ASSISTIDA (v2.56): o RH abre no
    computador do escritório e preenche COM A PESSOA PRESENTE. Guarda o e-mail
    do operador, que vai parar no manifesto da assinatura — é o que impede o
    documento de afirmar que a pessoa assinou sozinha na plataforma.

    `horas` encurta a validade. A sessão assistida usa poucas horas em vez das
    72 do convite: o link é para usar AGORA, com a pessoa na sala, e um link de
    preenchimento-por-terceiro válido por três dias é superfície de risco sem
    nenhuma contrapartida.
    """
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    acesso = AcessoMagico(
        candidato_id=candidato.id,
        token_hash=_hash(token),
        assistido_por=assistido_por,
        expira_em=datetime.now(timezone.utc) + timedelta(
            hours=horas if horas is not None else settings.magic_link_ttl_hours),
    )
    db.add(acesso)
    db.flush()
    return f"{base_url or settings.base_url}/c/{token}"


def operador_assistente(db: Session, token: str) -> str | None:
    """E-mail do RH que abriu esta sessão assistida, ou `None` se é remota.

    Consultado no momento da ASSINATURA, para o manifesto registrar quem operou
    o preenchimento. Devolve `None` para todo link comum — que é a esmagadora
    maioria e continua funcionando exatamente como antes.
    """
    acesso = db.scalar(select(AcessoMagico).where(AcessoMagico.token_hash == _hash(token)))
    if acesso is None or acesso.revogado:
        return None
    return acesso.assistido_por


def resolver_token(db: Session, token: str) -> Candidato | None:
    """Valida o token e devolve o candidato; None se inválido/expirado/revogado."""
    acesso = db.scalar(select(AcessoMagico).where(AcessoMagico.token_hash == _hash(token)))
    if acesso is None or acesso.revogado:
        return None
    if acesso.expira_em < datetime.now(timezone.utc):
        return None
    if acesso.usado_em is None:
        acesso.usado_em = datetime.now(timezone.utc)
    candidato = db.get(Candidato, acesso.candidato_id)
    # Identifica a pessoa no log desta requisição (v2.41). PRIMEIRO NOME, nunca
    # o token (é credencial) nem o CPF: é o menor dado que responde "quem
    # travou aqui?" quando alguém liga dizendo que não consegue.
    if candidato is not None:
        from app.services.contexto_log import definir_ator
        primeiro = (candidato.nome_completo or "").split()
        definir_ator(f"candidato:{primeiro[0] if primeiro else candidato.id}")
    return candidato
