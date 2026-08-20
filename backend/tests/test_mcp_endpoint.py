"""O endpoint `/mcp`: o 401 que dispara a descoberta, e o catálogo.

Duas coisas que falham em silêncio e por isso têm teste:

1. **Um `/mcp` que responde 200 com corpo de erro fica invisível.** É o
   `WWW-Authenticate` numa resposta **401** que faz o cliente descobrir o OAuth;
   sem isso, o "conectar" nunca aparece — com o servidor no ar, respondendo, e
   nada no log parecendo errado.
2. **Ferramenta cuja permissão não cabe no papel do assistente responde 403
   sempre.** Ninguém reporta: quem opera conclui que pediu a coisa errada
   (v2.88). O teste cobra que cada permissão declarada está entre as do
   `assistente_rh`.

Não precisa de banco — usa o `TestClient` sem credencial, que é justamente o
caminho do 401, e inspeciona o catálogo montado a partir das funções.
"""

import inspect
import os
import sys

os.environ.setdefault("MCP_ISSUER", "https://portal.exemplo.test")

falhas = []


def rodar():
    from fastapi.testclient import TestClient

    from app.api.mcp_endpoint import _catalogo
    from app.mcp.ferramentas import FERRAMENTAS, PERMISSAO_DA_FERRAMENTA
    from app.mcp_app import app
    from app.services.permissoes import permissoes_padrao

    http = TestClient(app, raise_server_exceptions=False)

    # ── 1. O 401 e o cabeçalho que ensina o cliente ───────────────────────
    r = http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    if r.status_code != 401:
        falhas.append(
            f"/mcp sem credencial respondeu {r.status_code}, esperado 401. O "
            "cliente só dispara a descoberta a partir de um 401 — com 200 ou "
            "403 o 'conectar' nunca aparece.")
    cabecalho = r.headers.get("www-authenticate", "")
    if "Bearer" not in cabecalho:
        falhas.append("o 401 não traz `WWW-Authenticate: Bearer`.")
    if "resource_metadata=" not in cabecalho:
        falhas.append(
            "o `WWW-Authenticate` não aponta o `resource_metadata` — é o fio "
            "que o cliente puxa para achar o servidor de autorização.")
    if "/.well-known/oauth-protected-resource" not in cabecalho:
        falhas.append("o `resource_metadata` não aponta para o documento certo.")

    # Token inventado tem que dar o MESMO 401 (não distinguir motivos).
    r2 = http.post("/mcp", headers={"Authorization": "Bearer nao-existe"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    if r2.status_code != 401:
        falhas.append(f"token inválido respondeu {r2.status_code}, esperado 401.")
    if r2.json() != r.json():
        falhas.append(
            "credencial ausente e credencial inválida devolvem respostas "
            "DIFERENTES — a distinção diz a quem testa qual credencial existiu.")

    # ── 2. GET também precisa do 401 ──────────────────────────────────────
    if http.get("/mcp").status_code != 401:
        falhas.append("GET /mcp sem credencial deveria responder 401.")

    # ── 3. O catálogo ─────────────────────────────────────────────────────
    catalogo = _catalogo()
    if len(catalogo) != len(FERRAMENTAS):
        falhas.append(f"o catálogo tem {len(catalogo)} ferramentas e existem "
                      f"{len(FERRAMENTAS)}.")
    for item in catalogo:
        if not item.get("description") or len(item["description"]) < 120:
            falhas.append(
                f"{item['name']}: descrição curta demais. É o que o modelo lê "
                "para escolher a ferramenta — descrição fraca faz a ferramenta "
                "errada ser chamada.")
        esquema = item.get("inputSchema") or {}
        if esquema.get("type") != "object":
            falhas.append(f"{item['name']}: inputSchema inválido.")
        for interno in ("db", "usuario"):
            if interno in (esquema.get("properties") or {}):
                falhas.append(
                    f"{item['name']}: expõe `{interno}` como parâmetro. É "
                    "injeção do servidor, não entrada do modelo.")

    # ── 4. Toda permissão declarada cabe no papel do assistente ───────────
    do_assistente = permissoes_padrao("assistente_rh")
    for fn in FERRAMENTAS:
        permissao = PERMISSAO_DA_FERRAMENTA.get(fn.__name__)
        if permissao is None:
            falhas.append(f"{fn.__name__} não declara permissão.")
        elif permissao not in do_assistente:
            falhas.append(
                f"{fn.__name__} exige {permissao!r}, que o papel "
                "`assistente_rh` NÃO tem — ela responderia 403 para todo mundo, "
                "sempre. Ou a ferramenta sai, ou a permissão é concedida de "
                "propósito (e o papel é estreito por desenho).")

    # ── 5. A permissão bate com a que a ROTA declara ──────────────────────
    # Sem isto, o MCP e a tela discordariam sobre o que aquele ato exige.
    esperado = {
        "buscar_candidato": "admissao:ler",
        "diagnostico_candidato": "admissao:ler",
        "listar_admissoes": "admissao:ler",
        "pendencias_tirvu": "colaboradores:ler",
        "cadastrar_talento": "selecao:escrever",
    }
    for nome, permissao in esperado.items():
        atual = PERMISSAO_DA_FERRAMENTA.get(nome)
        if atual != permissao:
            falhas.append(
                f"{nome} declara {atual!r}, mas a rota que ela chama exige "
                f"{permissao!r}. Divergência aqui faz o assistente e a tela "
                "discordarem sobre o que o ato exige.")

    # ── 6. `erros_recentes` continua fora ─────────────────────────────────
    if any(f.__name__ == "erros_recentes" for f in FERRAMENTAS):
        falhas.append(
            "`erros_recentes` voltou. A rota que ela serviria exige "
            "`sistema:telemetria`, que o papel do assistente não tem — "
            "responderia 403 sempre.")

    # ── 7. A checagem de permissão é EXECUTADA, não só declarada ──────────
    # (v2.67: teste que não executa a linha mutada não protege nada.)
    #
    # O papel `recepcao` não tem NENHUMA das permissões das ferramentas, então a
    # chamada precisa parar em `SemPermissao` — e parar ANTES de a ferramenta
    # chamar a rota. A sessão falsa devolve um conjunto vazio de permissões
    # (que é o que `permissoes_do_usuario` faz para papel sem registro) e
    # explode em qualquer outro uso, o que prova as duas coisas de uma vez.
    from app.mcp.ferramentas import SemPermissao
    from app.models.usuario_rh import UsuarioRH

    class _SessaoQueSoResolvePapel:
        """Responde à consulta do papel e recusa qualquer outro uso."""

        def scalar(self, *_a, **_k):
            return None  # papel não encontrado → conjunto vazio → nega

        def __getattr__(self, nome):
            raise AssertionError(
                f"a ferramenta chamou `db.{nome}` mesmo sem permissão — a "
                "checagem deveria ter parado antes de tocar a rota.")

    sem_papel = UsuarioRH(nome="X", email="x@y.z", senha_hash="x", ativo=True,
                          papel="recepcao")
    try:
        FERRAMENTAS[0](_SessaoQueSoResolvePapel(), sem_papel, busca="qualquer")
        falhas.append(
            "a ferramenta executou para um papel sem a permissão — o decorador "
            "não está conferindo nada.")
    except SemPermissao:
        pass  # exatamente o esperado
    except AssertionError as exc:
        falhas.append(str(exc))


rodar()

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("OK - 401 com WWW-Authenticate, catalogo descrito, e toda permissao "
      "cabendo no papel do assistente.")
