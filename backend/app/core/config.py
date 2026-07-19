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
    encaminhado = request.headers.get("x-forwarded-proto")
    if encaminhado:
        proto = encaminhado.split(",")[0].strip()
    else:
        # Sem X-Forwarded-Proto (proxy que não o envia): um host que não é local
        # é sempre acessado por HTTPS na prática — e o OAuth da Microsoft recusa
        # redirect_uri http em domínio público. Só localhost/IP interno fica http.
        so_host = host.split(":")[0]
        local = (so_host in ("localhost", "127.0.0.1", "::1")
                 or so_host.startswith(("10.", "192.168.", "172."))
                 or request.url.scheme == "https")
        proto = "http" if local and request.url.scheme != "https" else "https"
    return f"{proto}://{host}"


def ip_do_cliente(request) -> str | None:
    """IP real do cliente atrás do proxy (nginx/traefik enviam X-Forwarded-For /
    X-Real-IP; request.client.host seria o IP do container do proxy)."""
    encaminhado = request.headers.get("x-forwarded-for")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
