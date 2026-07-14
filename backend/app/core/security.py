from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext

from app.core.config import get_settings

# pbkdf2_sha256: implementação pura em Python, sem dependência binária.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"])


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="sessao-rh")


def criar_token_sessao(usuario_id: str) -> str:
    return _serializer().dumps({"sub": usuario_id})


def validar_token_sessao(token: str) -> str | None:
    """Devolve o id do usuário ou None se o token for inválido/expirado."""
    try:
        data = _serializer().loads(token, max_age=get_settings().rh_session_ttl_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("sub")
