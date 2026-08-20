"""O aplicativo do serviço MCP — processo próprio, separado da API do painel.

⚠️ **Não é um router do `main.py`, e a separação é decisão de desenho.** O doc
13 § 4 rejeitou pôr as rotas MCP dentro da API do painel: a superfície da IA não
se funde com a do humano, porque a IA executa instrução que veio de texto — e
neste sistema o texto vem de currículo e de campo livre.

Há também um motivo mecânico: os 40 routers do `main.py` usam `prefix="/api"`, e
os `.well-known` precisam estar na RAIZ do host (RFC 9728/8414). Encaixá-los lá
exigiria um `include_router` sem prefixo — a porta paralela que o projeto
combate.

**Mesmo código, processo separado**: reusa `get_db`, os serviços e os modelos.
O que não se reusa é o ciclo de vida: este processo **não roda migration** (quem
migra é a API — dois processos rodando `alembic upgrade` no mesmo banco é
corrida em produção, a regra que o `Dockerfile.transcricao` já segue).
"""

import logging
import time

from fastapi import FastAPI, Request

from app.api import mcp_autorizacao, mcp_endpoint, mcp_oauth, mcp_token
from app.core.config import get_settings
from app.services.logs import configurar as _configurar_logs

settings = get_settings()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
# Nome explícito, e não só o `LOG_SERVICO` do ambiente: se a variável faltar no
# compose, o padrão do módulo é "api" — e este serviço escreveria por cima do
# log da API, misturando duas histórias no mesmo arquivo justamente quando se
# está investigando qual dos dois falhou.
_configurar_logs("mcp")
log = logging.getLogger("mcp")

app = FastAPI(
    title=f"{settings.app_name} — assistente",
    # Sem docs públicas: este serviço fala com um cliente automatizado, e a
    # página do Swagger só ampliaria a superfície exposta.
    docs_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def log_requisicoes(request: Request, call_next):
    """Mesmo contrato do middleware da API: `req_id` antes de tudo.

    Sem ele, as linhas de log deste serviço não se ligam umas às outras e a
    investigação de um "não conectou" vira adivinhação (v2.41).
    """
    from app.services.contexto_log import definir

    req_id = definir()
    inicio = time.perf_counter()
    resposta = await call_next(request)
    resposta.headers["X-Request-Id"] = req_id
    log.info("method=%s path=%s status=%s ms=%s", request.method,
             request.url.path, resposta.status_code,
             round((time.perf_counter() - inicio) * 1000, 1))
    return resposta


@app.get("/mcp/health")
def health() -> dict:
    """Saúde do serviço, para o healthcheck do container.

    ⚠️ Em Python, não `curl`: a imagem não tem curl nem wget, e um healthcheck
    que falha sempre marca o container como *unhealthy* para sempre (v2.93).
    """
    from app.services import mcp_oauth as oauth

    configurado = bool((settings.mcp_issuer or "").strip())
    resposta = {"status": "ok" if configurado else "sem_issuer",
                "configurado": configurado}
    if configurado:
        resposta["resource"] = oauth.resource()
    return resposta


# Sem prefixo, de propósito: os `.well-known` moram na raiz por especificação.
app.include_router(mcp_oauth.router)
app.include_router(mcp_autorizacao.router)
app.include_router(mcp_token.router)
app.include_router(mcp_endpoint.router)
