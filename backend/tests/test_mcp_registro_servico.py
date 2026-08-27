"""O serviço do MCP registra um cliente SOZINHO — sem import de conveniência.

⚠️ **Este teste sobe `app.mcp_app` e mais nada.** É a diferença que importa: o
`test_mcp_oauth_fluxo.py` importa `app.models.candidato` à mão para resolver as
FKs (v2.64) — correto lá, porque ele não sobe app nenhuma —, e foi exatamente
isso que escondeu um defeito de PRODUÇÃO por uma versão inteira. O teste
consertava o ambiente que o serviço real não conserta.

O defeito (27/08/2026, `/register` devolvendo 500 em produção): `EventoAuditoria`
tem `ForeignKey("candidato.id")` e `registrar()` grava lá, mas o `mcp_app.py`
importava só os quatro módulos do MCP — `app/models/__init__.py` é VAZIO neste
projeto, quem registra tudo é a cadeia de imports do `main.py`, que este serviço
não tem. O SQLAlchemy só resolve FK no primeiro `flush`, então:

- o container SOBE e fica `Up`;
- `/mcp/health` responde `ok`;
- o `.well-known` serve JSON correto;
- e **só** o `/register` estoura, com `PendingRollbackError` mascarando a causa
  atrás de um 500 em texto puro.

Para quem conectava: *"Não foi possível registrar no serviço de login"*. Para
quem operava: nada fora do lugar. É a família do "container vivo e rota morta",
e a única defesa é um teste que suba o app COMO ELE SOBE em produção.

⚠️ Não acrescente `import app.models.<x>` aqui para "fazer passar" — isso
desliga o teste sem que nada denuncie. A correção é o import entrar no
`mcp_app.py`, que é o que roda no VPS.

Precisa de banco: roda no passo do CI com a stack de pé.
"""

import os
import sys
import uuid

os.environ.setdefault("MCP_ISSUER", "https://portal.exemplo.test")

from fastapi.testclient import TestClient  # noqa: E402

# O ÚNICO import do sistema. Se o serviço não registrar seus próprios modelos,
# é aqui que se descobre — e não na cara de quem tenta conectar.
from app.mcp_app import app  # noqa: E402

falhas = []
SUFIXO = uuid.uuid4().hex[:8]
REDIRECT = "https://claude.ai/api/mcp/auth_callback"

# `raise_server_exceptions=False`: sem isso a exceção do servidor sobe pelo
# TestClient e mata o script ANTES de imprimir qualquer coisa — a saída vazia
# passa por sucesso (v2.72.2). Com a flag, o 500 vira resposta e é reprovável.
cliente = TestClient(app, raise_server_exceptions=False)


def teste_register_grava_de_verdade():
    """O caminho que o Claude percorre ao adicionar o conector."""
    corpo = {
        "client_name": f"Teste registro {SUFIXO}",
        "redirect_uris": [REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    r = cliente.post("/register", json=corpo)

    if r.status_code == 500:
        falhas.append(
            "`POST /register` devolveu 500 — o serviço não consegue gravar. "
            "Se o log falar de FK que não acha tabela ('could not find table "
            "X'), o modelo dessa tabela NÃO está registrado no `metadata`: "
            "acrescente o import em `app/mcp_app.py` (com `# noqa: F401`), "
            "NUNCA neste teste. Detalhe: " + r.text[:400])
        return None
    if r.status_code != 201:
        falhas.append(
            f"`POST /register` devolveu {r.status_code}, esperado 201. "
            f"Corpo: {r.text[:400]}")
        return None

    dados = r.json()
    client_id = dados.get("client_id")
    if not client_id:
        falhas.append("`/register` respondeu 201 mas sem `client_id` no corpo.")
        return None
    if dados.get("token_endpoint_auth_method") != "none":
        falhas.append(
            "`token_endpoint_auth_method` deveria ser 'none' — o cliente é "
            "PÚBLICO e a prova dele é o PKCE.")
    if REDIRECT not in (dados.get("redirect_uris") or []):
        falhas.append(
            f"o `redirect_uris` devolvido não traz {REDIRECT!r} — o /authorize "
            "vai recusar o retorno.")
    return client_id


def teste_o_cliente_fica_no_banco(client_id):
    """201 não basta: o registro tem que ESTAR lá.

    Afirmar só sobre o status deixaria passar um commit que não commitou — e o
    sintoma seria "Aplicativo não reconhecido" no passo seguinte, longe daqui.
    """
    if client_id is None:
        return
    from app.core.db import SessionLocal
    from app.models.mcp_oauth import ClienteOAuth

    db = SessionLocal()
    try:
        achado = db.query(ClienteOAuth).filter(
            ClienteOAuth.client_id == client_id).one_or_none()
        if achado is None:
            falhas.append(
                f"`/register` respondeu 201, mas {client_id!r} NÃO está em "
                "`mcp_cliente_oauth`. O `/authorize` responderia 'Aplicativo "
                "não reconhecido' logo em seguida.")
            return
        if achado.origem != "dcr":
            falhas.append(
                f"`origem` é {achado.origem!r}, esperado 'dcr' (registro "
                "dinâmico) — é por ele que se distingue de um cliente criado "
                "por outro caminho.")
        # Limpa: teste que suja o banco faz a próxima execução falhar por um
        # motivo sem relação com o que se testa (v2.66).
        db.delete(achado)
        db.commit()
    finally:
        db.close()


def teste_health_do_servico():
    """Se o health responde e o /register não, o container parece saudável."""
    r = cliente.get("/mcp/health")
    if r.status_code != 200:
        falhas.append(f"`/mcp/health` devolveu {r.status_code}, esperado 200.")


_id = teste_register_grava_de_verdade()
teste_o_cliente_fica_no_banco(_id)
teste_health_do_servico()


def _reportar(itens: list[str]) -> None:
    """⚠️ ASCII no fallback: emoji levanta `UnicodeEncodeError` no console do
    Windows (cp1252) e mata o script ANTES de mostrar a causa — justamente
    quando ela importa, porque o teste está reprovando (v3.15)."""
    print("FALHOU:")
    for item in itens:
        try:
            print(f"  - {item}")
        except UnicodeEncodeError:
            print("  - " + item.encode("ascii", "replace").decode("ascii"))


if falhas:
    _reportar(falhas)
    sys.exit(1)
print("OK - o servico do MCP registra um cliente sozinho, e ele fica no banco.")
