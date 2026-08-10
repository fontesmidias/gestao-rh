import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.assinaturas import router as assinaturas_router
from app.api.configuracoes import router as configuracoes_router
from app.api.papeis import router as papeis_router
from app.api.auth_rh import router as auth_rh_router
from app.api.candidatos import router as candidatos_router
from app.api.documentos import router as documentos_router
from app.api.colaboradores import router as colaboradores_router
from app.api.entrada import router as entrada_router
from app.api.postos import router as postos_router
from app.api.incidencia_beneficios import router as incidencia_router
from app.api.creche import router as creche_router
from app.api.creche_publico import router as creche_publico_router
from app.api.desempenho import router as desempenho_router
from app.api.desenvolvimento import router as desenvolvimento_router
from app.api.portal import router as portal_router
from app.api.testes import router as testes_router
from app.api.testagem import router as testagem_router
from app.api.provas import router as provas_router
from app.api.modelos import router as modelos_router
from app.api.talentos import router as talentos_router
from app.api.crm import router as crm_router
from app.api.diagnostico import router as diagnostico_router
from app.api.ficha import router as ficha_router
from app.api.revisao import router as revisao_router
from app.api.lixeira import router as lixeira_router
from app.api.arquivo import router as arquivo_router
from app.api.solicitacoes_assinatura import router as solicitacoes_router
from app.api.solicitacoes_externo import router as solicitacoes_externo_router
from app.api.autorizacao_equipe import router as autorizacao_equipe_router
from app.api.marca import router as marca_router
from app.api.organizacao import router as organizacao_router
from app.api.rh_ficha import router as rh_ficha_router
from app.api.minutario import router as minutario_router
from app.api.vagas import router as vagas_router
from app.api.entrevistas import router as entrevistas_router
from app.api.roteiros_entrevista import router as roteiros_entrevista_router
from app.api.health import router as health_router
from app.api.logs import router as logs_router
from app.api.telemetria import router as telemetria_router
from app.core.bootstrap import criar_admin_inicial
from app.core.config import get_settings, ip_do_cliente
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
# Log também em ARQUIVO (v2.29): o do container morre no restart, e foi só por
# sorte que o incidente do Defender (v2.28) ainda tinha rastro para ler. O
# stdout continua igual — se o volume não estiver montado, degrada para ele.
from app.services.logs import configurar as _configurar_logs  # noqa: E402

_configurar_logs()
telemetria = logging.getLogger("telemetria")

app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.exception_handler(RequestValidationError)
async def log_422(request: Request, exc: RequestValidationError):
    """Auditoria de erros de validação: registra o corpo exato que foi recusado
    (senhas mascaradas) para nunca mais debugar um 422 às cegas."""
    corpo = (await request.body())[:2000].decode("utf-8", "replace")
    for chave in ("senha", "password"):
        if chave in corpo:
            corpo = "<contém credencial — mascarado>"
            break
    erros = [
        {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg", ""),
         "type": e.get("type", "")}
        for e in exc.errors()
    ]
    telemetria.warning("422 path=%s erros=%s corpo=%r", request.url.path, erros, corpo)
    return JSONResponse(status_code=422, content={"detail": erros})


@app.exception_handler(Exception)
async def log_erro_interno(request: Request, exc: Exception):
    """Rede de segurança contra erro não tratado (ex.: ValidationError manual,
    DataError de truncamento de coluna) — sem isso, o Starlette devolve 500 em
    texto puro e o front não tem o que mostrar ao RH (feedback de campo
    2026-07-27: "não salva e não diz o motivo").

    NUNCA ecoar str(exc) ao cliente: a mensagem de erro do Postgres para
    truncamento de coluna inclui o VALOR que estourou — num sistema de RH isso
    pode ser CPF. O motivo real vai só para o log; o cliente recebe um id de
    correlação para localizá-lo."""
    correlacao = uuid.uuid4().hex[:12]
    telemetria.exception("erro_interno id=%s path=%s", correlacao, request.url.path)
    return JSONResponse(status_code=500,
                        content={"detail": "erro_interno", "id": correlacao})


@app.middleware("http")
async def log_requisicoes(request: Request, call_next):
    """Telemetria de uso: método, rota, status e duração de cada requisição.
    Tokens de link mágico são mascarados para não vazarem em log."""
    from app.services.contexto_log import definir

    # Um identificador por requisição, ANTES de qualquer coisa acontecer: todo
    # log emitido daqui para baixo — storage, e-mail, serviço no fundo da pilha
    # — sai com ele. É o que permite pegar um erro e ver o que veio antes.
    req_id = definir()
    inicio = time.perf_counter()
    resposta = await call_next(request)
    duracao_ms = round((time.perf_counter() - inicio) * 1000, 1)
    # Devolve o id ao cliente: quando alguém relata um problema com print da
    # tela, o cabeçalho dá o fio exato para puxar no log.
    resposta.headers["X-Request-Id"] = req_id
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
        ip_do_cliente(request) or "-",
    )
    return resposta

app.include_router(health_router, prefix="/api")
app.include_router(telemetria_router, prefix="/api")
app.include_router(logs_router, prefix="/api")
app.include_router(auth_rh_router, prefix="/api")
app.include_router(candidatos_router, prefix="/api")
app.include_router(ficha_router, prefix="/api")
app.include_router(documentos_router, prefix="/api")
app.include_router(entrada_router, prefix="/api")
app.include_router(colaboradores_router, prefix="/api")
app.include_router(postos_router, prefix="/api")
app.include_router(incidencia_router, prefix="/api")
app.include_router(creche_router, prefix="/api")
app.include_router(creche_publico_router, prefix="/api")
app.include_router(portal_router, prefix="/api")
app.include_router(desenvolvimento_router, prefix="/api")
app.include_router(desempenho_router, prefix="/api")
app.include_router(testes_router, prefix="/api")
app.include_router(testagem_router, prefix="/api")
app.include_router(provas_router, prefix="/api")
app.include_router(modelos_router, prefix="/api")
app.include_router(talentos_router, prefix="/api")
app.include_router(crm_router, prefix="/api")
app.include_router(diagnostico_router, prefix="/api")
app.include_router(assinaturas_router, prefix="/api")
app.include_router(revisao_router, prefix="/api")
app.include_router(rh_ficha_router, prefix="/api")
app.include_router(configuracoes_router, prefix="/api")
app.include_router(papeis_router, prefix="/api")
app.include_router(lixeira_router, prefix="/api")
app.include_router(arquivo_router, prefix="/api")
app.include_router(solicitacoes_router, prefix="/api")
app.include_router(solicitacoes_externo_router, prefix="/api")
app.include_router(autorizacao_equipe_router, prefix="/api")
app.include_router(marca_router, prefix="/api")
app.include_router(organizacao_router, prefix="/api")
app.include_router(minutario_router, prefix="/api")
app.include_router(vagas_router, prefix="/api")
app.include_router(entrevistas_router, prefix="/api")
app.include_router(roteiros_entrevista_router, prefix="/api")
