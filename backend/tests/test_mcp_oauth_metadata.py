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


def teste_cliente_publico_e_cimd():
    """Os dois campos que, JUNTOS, permitem o cliente identificar-se por CIMD."""
    metodos = autorizador.get("token_endpoint_auth_methods_supported")
    if metodos != ["none"]:
        falhas.append(
            f"`token_endpoint_auth_methods_supported` é {metodos!r}, esperado "
            "['none'] — o cliente é PÚBLICO e a prova dele é o PKCE.")
    if autorizador.get("client_id_metadata_document_supported") is not True:
        falhas.append(
            "`client_id_metadata_document_supported` não é `true`. ⚠️ Se o CIMD "
            "não for implementado de fato, REMOVA este campo em vez de deixá-lo "
            "mentindo — anunciar e falhar é pior que não anunciar.")


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
          teste_pkce_anunciado, teste_cliente_publico_e_cimd, teste_iss_anunciado,
          teste_endpoints_sao_do_issuer, teste_issuer_vazio_recusa):
    t()

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("OK - os metadados trazem tudo que o cliente precisa para conectar.")
