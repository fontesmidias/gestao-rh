"""Os metadados de descoberta — sem eles o "conectar" nem aparece.

Cada campo aqui é exigido pela especificação de autorização do MCP, e a falta de
qualquer um deles não produz erro no nosso lado: o cliente simplesmente desiste
de conectar, com uma mensagem genérica de "não foi possível". O sintoma fica
longe da causa, que é o motivo de este teste existir.

Roda com um `MCP_ISSUER` de mentira e afirma sobre o dicionário REAL devolvido
pelas funções — não sobre o texto do arquivo. Afirmar sobre o texto passaria com
a função devolvendo outra coisa (a lição da v2.67: teste que não executa a linha
mutada não protege nada).

Precisa do venv do backend (importa `app.api.mcp_oauth`), então roda no passo
que já tem as dependências.
"""

import os
import sys

os.environ.setdefault("MCP_ISSUER", "https://portal.exemplo.test")

from app.api.mcp_oauth import (  # noqa: E402
    metadata_do_autorizador,
    metadata_do_recurso,
)
from app.services import mcp_oauth as oauth  # noqa: E402

falhas = []
recurso = metadata_do_recurso()
autorizador = metadata_do_autorizador()


def teste_recurso_aponta_para_si():
    if recurso.get("resource") != oauth.resource():
        falhas.append(
            f"`resource` é {recurso.get('resource')!r} mas deveria ser "
            f"{oauth.resource()!r}. Ele precisa bater EXATAMENTE com a URL que a "
            "pessoa digita ao adicionar o conector.")
    servidores = recurso.get("authorization_servers") or []
    if len(servidores) != 1:
        falhas.append(
            f"`authorization_servers` tem {len(servidores)} itens. O cliente usa "
            "o PRIMEIRO e não tenta os demais — uma lista maior esconderia qual "
            "está valendo.")


def teste_offline_access_nao_entra_no_recurso():
    """Refresh token não é exigência do RECURSO — a spec pede que ele não apareça."""
    if "offline_access" in (recurso.get("scopes_supported") or []):
        falhas.append(
            "`offline_access` está no `scopes_supported` do protected resource. "
            "Ele pertence ao authorization server, não ao recurso.")


def teste_pkce_anunciado():
    """Sem este campo o cliente conclui que não há PKCE e RECUSA continuar."""
    metodos = autorizador.get("code_challenge_methods_supported")
    if metodos != ["S256"]:
        falhas.append(
            f"`code_challenge_methods_supported` é {metodos!r}, esperado "
            "['S256']. Sem ele o cliente recusa o fluxo; com 'plain' junto, o "
            "desafio vira o próprio segredo (o que o OAuth 2.1 fechou).")


def teste_cliente_publico():
    metodos = autorizador.get("token_endpoint_auth_methods_supported")
    if metodos != ["none"]:
        falhas.append(
            f"`token_endpoint_auth_methods_supported` é {metodos!r}, esperado "
            "['none'] — o cliente é PÚBLICO e a prova dele é o PKCE.")


def teste_cimd_anunciado_so_se_implementado():
    """Anúncio e implementação andam JUNTOS — nunca um sem o outro.

    ⚠️ Este teste já existiu ao contrário, EXIGINDO o anúncio, e a mensagem dele
    avisava: *"se o CIMD não for implementado de fato, REMOVA este campo em vez
    de deixá-lo mentindo"*. O aviso estava certo e o teste travava o lado errado
    — então o campo ficou `true` sem implementação e **quebrou o "Vincular" em
    produção** (26/08/2026): o Claude viu o anúncio, abandonou o `/register` e
    mandou a URL do próprio metadata como `client_id`. O `resolver_cliente` só
    consulta `mcp_cliente_oauth`, que estava VAZIA — "Aplicativo não reconhecido"
    em toda tentativa, com o serviço perfeitamente no ar.

    A regra que fica: **capacidade anunciada é promessa**, e a única forma de
    não quebrá-la é o teste comparar o anúncio com o código que a cumpre. Por
    isso a asserção é bidirecional — ligar o campo sem implementar reprova, e
    implementar sem ligar também (aí o trabalho feito não serve para nada).

    O sinal de implementação é `resolver_cliente` saber tratar `client_id` que
    é URL. Enquanto ele só fizer o `select` na tabela, não há CIMD.
    """
    import pathlib
    import re

    anunciado = autorizador.get("client_id_metadata_document_supported") is True

    servico = pathlib.Path(oauth.__file__).read_text(encoding="utf-8")
    m = re.search(r'def resolver_cliente\(.*?(?=\ndef |\Z)', servico, re.S)
    if not m:
        falhas.append("não achei `resolver_cliente` para conferir o par.")
        return
    corpo = m.group(0)
    # Comentário e docstring citam CIMD sem implementá-lo (a armadilha da v2.71):
    # afirmar sobre o texto cru daria implementado por causa de uma menção.
    codigo = "\n".join(l for l in corpo.splitlines()
                       if not l.lstrip().startswith("#"))
    implementado = bool(re.search(r"cimd|https?://|urlsplit|httpx|requests", codigo))

    if anunciado and not implementado:
        falhas.append(
            "`client_id_metadata_document_supported: true` está anunciado, mas "
            "`resolver_cliente` só procura na tabela `mcp_cliente_oauth`. O "
            "cliente vai ABANDONAR o `/register` e mandar uma URL como "
            "`client_id` — e receber 'Aplicativo não reconhecido' sempre. "
            "Implemente CIMD (com allowlist de host: é requisição de saída para "
            "destino que o cliente escolhe) ou retire o anúncio.")
    if implementado and not anunciado:
        falhas.append(
            "`resolver_cliente` parece tratar CIMD, mas o campo "
            "`client_id_metadata_document_supported` não está anunciado — sem o "
            "anúncio nenhum cliente usa o caminho, e o código fica órfão.")


def teste_iss_anunciado():
    """RFC 9207: quem emite `iss` precisa anunciar que emite."""
    if autorizador.get("authorization_response_iss_parameter_supported") is not True:
        falhas.append(
            "`authorization_response_iss_parameter_supported` não é `true`. "
            "Emitir `iss` sem anunciar faz o cliente ignorar a proteção contra "
            "mix-up.")


def teste_endpoints_sao_do_issuer():
    base = oauth.issuer()
    if autorizador.get("issuer") != base:
        falhas.append(f"`issuer` divergente: {autorizador.get('issuer')!r}")
    for campo, sufixo in (("authorization_endpoint", "/authorize"),
                          ("token_endpoint", "/token"),
                          ("registration_endpoint", "/register")):
        if autorizador.get(campo) != f"{base}{sufixo}":
            falhas.append(
                f"`{campo}` é {autorizador.get(campo)!r}, esperado {base}{sufixo}")
    if "offline_access" not in (autorizador.get("scopes_supported") or []):
        falhas.append(
            "`offline_access` precisa estar no authorization server — é o que "
            "sinaliza ao cliente que ele pode pedir refresh token.")


def teste_issuer_vazio_recusa():
    """Vazio RECUSA, em vez de cair no BASE_URL.

    O padrão do `base_url` é `http://localhost:8090`. Um provedor OAuth
    anunciando isso em produção passaria na descoberta e falharia no callback,
    com o sintoma longe da causa.
    """
    from app.core.config import get_settings

    get_settings.cache_clear()
    anterior = os.environ.get("MCP_ISSUER")
    os.environ["MCP_ISSUER"] = ""
    try:
        oauth.issuer()
        falhas.append(
            "MCP_ISSUER vazio NÃO recusou. Cair num padrão silencioso faria o "
            "provedor anunciar um endereço que não é o dele.")
    except RuntimeError:
        pass
    finally:
        if anterior is not None:
            os.environ["MCP_ISSUER"] = anterior
        get_settings.cache_clear()


for t in (teste_recurso_aponta_para_si, teste_offline_access_nao_entra_no_recurso,
          teste_pkce_anunciado, teste_cliente_publico,
          teste_cimd_anunciado_so_se_implementado, teste_iss_anunciado,
          teste_endpoints_sao_do_issuer, teste_issuer_vazio_recusa):
    t()

def _reportar(itens: list[str]) -> None:
    """Imprime as falhas em qualquer console.

    ⚠️ O console do Windows (cp1252) NÃO imprime emoji: um `print` com "⚠️"
    levanta `UnicodeEncodeError` e o teste morre ANTES de mostrar a mensagem —
    justamente quando ela importa, porque o teste está reprovando. O defeito
    aparece como traceback de encoding, que não fala nada sobre a causa real.
    """
    print("FALHOU:")
    for item in itens:
        try:
            print(f"  - {item}")
        except UnicodeEncodeError:
            print("  - " + item.encode("ascii", "replace").decode("ascii"))


if falhas:
    _reportar(falhas)
    sys.exit(1)
print("OK - os metadados trazem tudo que o cliente precisa para conectar.")
