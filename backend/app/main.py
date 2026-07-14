from fastapi import FastAPI

from app.api.auth_rh import router as auth_rh_router
from app.api.candidatos import router as candidatos_router
from app.api.health import router as health_router
from app.core.bootstrap import criar_admin_inicial
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine

settings = get_settings()

# Provisório até o módulo de migrações (Alembic) entrar.
Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    criar_admin_inicial(_db)

app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(health_router, prefix="/api")
app.include_router(auth_rh_router, prefix="/api")
app.include_router(candidatos_router, prefix="/api")
