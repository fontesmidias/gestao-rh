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


def _serializer_reset() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="reset-senha-rh")


def criar_token_reset(usuario_id: str, senha_hash: str) -> str:
    """Token de redefinição stateless: carrega um fragmento do hash atual da
    senha — quando a senha muda, o hash muda e o token deixa de valer, o que
    o torna de uso único sem precisar de estado no banco."""
    return _serializer_reset().dumps({"sub": usuario_id, "h": senha_hash[-16:]})


def validar_token_reset(token: str, max_age_s: int = 1800) -> dict | None:
    """Devolve {'sub': id, 'h': fragmento} ou None se inválido/expirado (30 min)."""
    try:
        return _serializer_reset().loads(token, max_age=max_age_s)
    except (BadSignature, SignatureExpired):
        return None
