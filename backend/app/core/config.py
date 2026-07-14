from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração 100% via variáveis de ambiente (.env). Nenhum valor de infra no código."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Portal de Admissão Green House"
    environment: str = "development"
    secret_key: str = "troque-me"
    base_url: str = "http://localhost:8090"

    database_url: str = "postgresql+psycopg://admissao:admissao@db:5432/admissao"

    redis_url: str = "redis://redis:6379/0"

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "troque-me"
    minio_bucket: str = "admissao"
    minio_secure: bool = False

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "rh@greenhousedf.com.br"

    # Admin inicial do RH: criado no primeiro start se não existir nenhum usuário.
    rh_admin_email: str = ""
    rh_admin_password: str = ""
    rh_session_ttl_hours: int = 12

    magic_link_ttl_hours: int = 72
    otp_ttl_minutes: int = 10
    retention_days: int = 90


def base_url_publica(request) -> str:
    """URL pública derivada da própria requisição (Host/X-Forwarded-*), para que
    links gerados (link mágico, reset de senha, callback OAuth) funcionem em
    qualquer forma de acesso — localhost, IP:porta, domínio ou subdomínio — sem
    depender do BASE_URL do .env (que fica só como último recurso)."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if not host:
        return get_settings().base_url
    host = host.split(",")[0].strip()
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
    return f"{proto.split(',')[0].strip()}://{host}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
