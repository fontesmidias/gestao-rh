"""Descoberta e registro do provedor OAuth — o que faz o "conectar" aparecer.

Estas rotas são **públicas por especificação**, e cada uma é pública por um
motivo diferente:

- os dois `.well-known` porque a descoberta acontece ANTES de existir qualquer
  credencial (é o cliente perguntando "como eu me autentico aqui?");
- o `/register` porque a RFC 7591 o define assim — e é aceitável porque
  **registrar NÃO dá acesso**: sem uma pessoa fazer login em `/authorize` e
  autorizar, o cliente registrado não obtém token nenhum.

⚠️ **Não estão sob `/api`.** As RFCs 9728 e 8414 exigem os `.well-known` na
RAIZ do host. Isso é parte do motivo de o MCP viver em serviço próprio (doc 17
§ 4.4): enfiá-las no `main.py`, cujos 40 routers usam `prefix="/api"`, exigiria
um `include_router` sem prefixo — a porta paralela que o projeto combate.

⚠️ **O nginx precisa rotear os `.well-known` explicitamente.** Medido em
20/08/2026: sem `location` próprio, `/.well-known/oauth-protected-resource`
devolve **HTTP 200 com o HTML do SPA**, o Claude tenta lê-lo como JSON e a
conexão falha dizendo que não alcançou o servidor — com tudo no ar e nada no log
parecendo errado. É o mesmo mecanismo do incidente da tela branca (v2.29).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException

from app.core.config import ip_do_cliente
from app.core.db import get_db
from app.services import mcp_oauth as oauth
from app.services.auditoria import registrar
from app.services.limite import exigir

router = APIRouter(tags=["mcp-oauth"])


# ── Descoberta ────────────────────────────────────────────────────────────────


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def metadata_do_recurso() -> dict:
    """RFC 9728 — diz ao cliente qual é o servidor de autorização.

    Servido nas DUAS URLs de propósito: a RFC manda sufixar com o caminho do
    recurso (`/mcp`), e clientes existentes ainda pedem a raiz. Duas rotas, uma
    resposta — barato, e evita um "não conectou" por causa de um sufixo.

    ⚠️ `offline_access` **não entra** em `scopes_supported`: refresh token não é
    exigência do RECURSO, e a spec pede que o resource server não o anuncie.
    """
    return {
        "resource": oauth.resource(),
        # UM item. O Claude usa o primeiro e não tenta os demais — uma lista de
        # dois esconderia qual está valendo.
        "authorization_servers": [oauth.issuer()],
        "scopes_supported": [oauth.ESCOPO],
        "bearer_methods_supported": ["header"],
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
def metadata_do_autorizador() -> dict:
    """RFC 8414 — onde ficam `/authorize`, `/token` e `/register`.

    Cada campo abaixo é necessário para o "conectar" funcionar:

    - `code_challenge_methods_supported: ["S256"]` — sem ele o cliente conclui
      que não há PKCE e **recusa continuar** (a spec manda recusar).
    - `token_endpoint_auth_methods_supported: ["none"]` **junto com**
      `client_id_metadata_document_supported: true` são a condição para o
      cliente usar CIMD; anunciar um sem o outro faz cair no registro dinâmico.
    - `authorization_response_iss_parameter_supported: true` — obrigatório para
      quem emite `iss` (RFC 9207), e nós emitimos.
    """
    base = oauth.issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        # Aqui `offline_access` ENTRA: é o autorizador falando de si, e é o que
        # sinaliza ao cliente que ele pode pedir refresh token.
        "scopes_supported": [oauth.ESCOPO, "offline_access"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
    }


# ── Registro dinâmico (RFC 7591) ──────────────────────────────────────────────


class RegistroIn(BaseModel):
    """O corpo do `/register`.

    `extra` fica livre: a RFC 7591 permite campos que não usamos (`logo_uri`,
    `client_uri`, `contacts`), e recusar o desconhecido faria o registro falhar
    por um campo cosmético.
    """

    model_config = {"extra": "allow"}

    client_name: str | None = None
    redirect_uris: list[str] = Field(default_factory=list)


def _uri_aceitavel(uri: str) -> bool:
    """`https` em domínio real, ou loopback — nada mais.

    `http` em host público seria o token de acesso trafegando em claro; e um
    fragmento (`#`) na URI é o vetor clássico de vazar o code para script de
    terceiro na página de destino.
    """
    from urllib.parse import urlsplit

    if not uri or "#" in uri:
        return False
    p = urlsplit(uri)
    if p.scheme == "https" and p.hostname:
        return True
    return p.scheme == "http" and (p.hostname or "") in ("localhost", "127.0.0.1", "::1")


@router.post("/register", status_code=201)
def registrar_cliente(payload: RegistroIn, request: Request,
                      db: Session = Depends(get_db)) -> dict:
    """Cadastra o cliente que vai PEDIR autorização.

    ⚠️ **Público por definição do protocolo, e isso não é um buraco.**
    Registrar-se não concede nada: sem uma pessoa fazer login em `/authorize` e
    autorizar, o cliente registrado não obtém token nenhum. Quem ler isto e
    quiser "fechar o buraco" fechando o endpoint vai quebrar a conexão para
    todo mundo.

    O que limita o abuso é o rate limit por IP e o fato de o registro ficar na
    auditoria com o IP de origem — o que permite investigar depois.
    """
    ip = ip_do_cliente(request) or "?"
    exigir(f"mcp-register:ip:{ip}", maximo=10, janela_s=3600)

    uris = [u.strip() for u in (payload.redirect_uris or []) if u and u.strip()]
    if not uris:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_redirect_uri",
            "error_description": "redirect_uris é obrigatório.",
        })
    if len(uris) > 5:
        raise HTTPException(status_code=400, detail={
            "error": "invalid_redirect_uri",
            "error_description": "no máximo 5 redirect_uris.",
        })
    for uri in uris:
        if not _uri_aceitavel(uri):
            raise HTTPException(status_code=400, detail={
                "error": "invalid_redirect_uri",
                "error_description": (
                    f"{uri!r} não é aceita: use https:// em domínio real ou "
                    "http://localhost, e sem fragmento (#)."
                ),
            })

    registro = oauth.registrar_cliente(
        db, client_name=(payload.client_name or "Aplicativo"),
        redirect_uris=uris, origem="dcr", ip=ip)
    registrar(db, "mcp_cliente_registrado", ator="sistema",
              detalhe={"client_id": registro.client_id,
                       "nome": registro.client_name, "ip": ip})
    db.commit()

    return {
        "client_id": registro.client_id,
        "client_id_issued_at": int(registro.criado_em.timestamp()),
        "client_name": registro.client_name,
        "redirect_uris": registro.redirect_uris,
        # Cliente PÚBLICO: a prova é o PKCE, não um segredo. Devolver um
        # `client_secret` que ninguém confere daria a impressão de uma defesa
        # inexistente.
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
