import logging
import time

from fastapi import FastAPI, Request

from app.api.assinaturas import router as assinaturas_router
from app.api.configuracoes import router as configuracoes_router
from app.api.auth_rh import router as auth_rh_router
from app.api.candidatos import router as candidatos_router
from app.api.documentos import router as documentos_router
from app.api.ficha import router as ficha_router
from app.api.revisao import router as revisao_router
from app.api.health import router as health_router
from app.core.bootstrap import criar_admin_inicial
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine

settings = get_settings()

# Schema é responsabilidade do Alembic (docker-entrypoint roda `alembic upgrade head`).
# Em desenvolvimento local sem migrations aplicadas: ALEMBIC_AUTO_CREATE=1 usa create_all.
import os

if os.getenv("ALEMBIC_AUTO_CREATE") == "1":
    Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    criar_admin_inicial(_db)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
telemetria = logging.getLogger("telemetria")

app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.middleware("http")
async def log_requisicoes(request: Request, call_next):
    """Telemetria de uso: método, rota, status e duração de cada requisição.
    Tokens de link mágico são mascarados para não vazarem em log."""
    inicio = time.perf_counter()
    resposta = await call_next(request)
    duracao_ms = round((time.perf_counter() - inicio) * 1000, 1)
    caminho = request.url.path
    if "/c/" in caminho:  # mascara o token do candidato
        partes = caminho.split("/")
        idx = partes.index("c") + 1
        if idx < len(partes) and len(partes[idx]) > 8:
            partes[idx] = partes[idx][:6] + "***"
        caminho = "/".join(partes)
    telemetria.info(
        "method=%s path=%s status=%s ms=%s ip=%s",
        request.method, caminho, resposta.status_code, duracao_ms,
        request.headers.get("x-real-ip", request.client.host if request.client else "-"),
    )
    return resposta

app.include_router(health_router, prefix="/api")
app.include_router(auth_rh_router, prefix="/api")
app.include_router(candidatos_router, prefix="/api")
app.include_router(ficha_router, prefix="/api")
app.include_router(documentos_router, prefix="/api")
app.include_router(assinaturas_router, prefix="/api")
app.include_router(revisao_router, prefix="/api")
app.include_router(configuracoes_router, prefix="/api")
