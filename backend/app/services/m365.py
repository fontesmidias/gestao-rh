"""Envio de e-mail via Microsoft 365 (OAuth 2.0 + Microsoft Graph).

Fluxo: RH conecta a conta uma vez pelo popup (authorization code + offline_access);
guardamos o refresh_token e enviamos e-mails via Graph /me/sendMail.
Requer um aplicativo registrado no Entra ID (client_id/tenant/secret no painel).
"""

import base64
import logging

import httpx
from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

log = logging.getLogger(__name__)

CHAVES_M365 = ("m365_client_id", "m365_tenant_id", "m365_client_secret",
               "m365_refresh_token", "m365_conta")
ESCOPOS = "offline_access Mail.Send User.Read"


def config_m365(db: Session) -> dict:
    return ler_config(db, CHAVES_M365)


def url_autorizacao(db: Session, redirect_uri: str, state: str) -> str:
    cfg = config_m365(db)
    tenant = cfg.get("m365_tenant_id", "common") or "common"
    params = httpx.QueryParams({
        "client_id": cfg.get("m365_client_id", ""),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": ESCOPOS,
        "state": state,
        "prompt": "select_account",
    })
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{params}"


def _token_endpoint(cfg: dict) -> str:
    tenant = cfg.get("m365_tenant_id", "common") or "common"
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def trocar_codigo(db: Session, codigo: str, redirect_uri: str) -> str:
    """Troca o authorization code por tokens; grava o refresh_token. Devolve a conta."""
    cfg = config_m365(db)
    r = httpx.post(_token_endpoint(cfg), data={
        "client_id": cfg.get("m365_client_id", ""),
        "client_secret": cfg.get("m365_client_secret", ""),
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": redirect_uri,
        "scope": ESCOPOS,
    }, timeout=30)
    r.raise_for_status()
    tokens = r.json()

    me = httpx.get("https://graph.microsoft.com/v1.0/me",
                   headers={"Authorization": f"Bearer {tokens['access_token']}"},
                   timeout=30).json()
    conta = me.get("mail") or me.get("userPrincipalName", "")

    gravar_config(db, {"m365_refresh_token": tokens["refresh_token"], "m365_conta": conta})
    db.commit()
    return conta


def _access_token(db: Session) -> str | None:
    cfg = config_m365(db)
    if not cfg.get("m365_refresh_token"):
        return None
    r = httpx.post(_token_endpoint(cfg), data={
        "client_id": cfg.get("m365_client_id", ""),
        "client_secret": cfg.get("m365_client_secret", ""),
        "grant_type": "refresh_token",
        "refresh_token": cfg["m365_refresh_token"],
        "scope": ESCOPOS,
    }, timeout=30)
    if r.status_code != 200:
        log.error("Falha ao renovar token M365: %s", r.text[:300])
        return None
    tokens = r.json()
    if tokens.get("refresh_token"):
        gravar_config(db, {"m365_refresh_token": tokens["refresh_token"]})
        db.commit()
    return tokens["access_token"]


def enviar_via_graph(db: Session, destinatario: str, assunto: str,
                     corpo_texto: str, corpo_html: str | None = None,
                     anexos: list[tuple[str, bytes]] | None = None) -> bool:
    token = _access_token(db)
    if token is None:
        return False
    mensagem = {
        "message": {
            "subject": assunto,
            "body": {"contentType": "HTML" if corpo_html else "Text",
                     "content": corpo_html or corpo_texto},
            "toRecipients": [{"emailAddress": {"address": destinatario}}],
            "attachments": [
                {"@odata.type": "#microsoft.graph.fileAttachment",
                 "name": nome, "contentType": "application/pdf",
                 "contentBytes": base64.b64encode(dados).decode()}
                for nome, dados in (anexos or [])
            ],
        },
        "saveToSentItems": True,
    }
    r = httpx.post("https://graph.microsoft.com/v1.0/me/sendMail",
                   headers={"Authorization": f"Bearer {token}"},
                   json=mensagem, timeout=30)
    if r.status_code == 202:
        log.info("E-mail M365/Graph enviado para %s: %s", destinatario, assunto)
        return True
    log.error("Graph sendMail falhou (%s): %s", r.status_code, r.text[:300])
    return False


def desconectar(db: Session) -> None:
    gravar_config(db, {"m365_refresh_token": "", "m365_conta": ""})
    db.commit()
