"""Envio de e-mail via Google (OAuth 2.0 + Gmail API) — o "Fazer login com o
Google" recomendado pela própria Google no lugar de senhas de app.

Fluxo: RH conecta a conta uma vez pelo popup (authorization code + offline);
guardamos o refresh_token e enviamos e-mails via Gmail API users/me/messages/send.
Requer um OAuth Client ID (tipo Web) criado no Google Cloud Console.
"""

import base64
import logging
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

log = logging.getLogger(__name__)

CHAVES_GMAIL = ("gmail_client_id", "gmail_client_secret",
                "gmail_refresh_token", "gmail_conta")
ESCOPOS = "https://www.googleapis.com/auth/gmail.send email"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def config_gmail(db: Session) -> dict:
    return ler_config(db, CHAVES_GMAIL)


def url_autorizacao(db: Session, redirect_uri: str, state: str) -> str:
    cfg = config_gmail(db)
    params = httpx.QueryParams({
        "client_id": cfg.get("gmail_client_id", ""),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": ESCOPOS,
        "state": state,
        # offline + consent garantem que o refresh_token venha na primeira conexão.
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"


def trocar_codigo(db: Session, codigo: str, redirect_uri: str) -> str:
    """Troca o authorization code por tokens; grava o refresh_token. Devolve a conta."""
    cfg = config_gmail(db)
    r = httpx.post(_TOKEN_URL, data={
        "client_id": cfg.get("gmail_client_id", ""),
        "client_secret": cfg.get("gmail_client_secret", ""),
        "grant_type": "authorization_code",
        "code": codigo,
        "redirect_uri": redirect_uri,
    }, timeout=30)
    r.raise_for_status()
    tokens = r.json()

    info = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo",
                     headers={"Authorization": f"Bearer {tokens['access_token']}"},
                     timeout=30).json()
    conta = info.get("email", "")

    if not tokens.get("refresh_token"):
        raise RuntimeError("O Google não devolveu o refresh token — desconecte o app em "
                           "myaccount.google.com/permissions e conecte de novo.")
    gravar_config(db, {"gmail_refresh_token": tokens["refresh_token"], "gmail_conta": conta})
    db.commit()
    return conta


def _access_token(db: Session) -> str | None:
    cfg = config_gmail(db)
    if not cfg.get("gmail_refresh_token"):
        return None
    r = httpx.post(_TOKEN_URL, data={
        "client_id": cfg.get("gmail_client_id", ""),
        "client_secret": cfg.get("gmail_client_secret", ""),
        "grant_type": "refresh_token",
        "refresh_token": cfg["gmail_refresh_token"],
    }, timeout=30)
    if r.status_code != 200:
        log.error("Falha ao renovar token Google: %s", r.text[:300])
        return None
    return r.json()["access_token"]


def enviar_via_gmail(db: Session, destinatario: str, assunto: str,
                     corpo_texto: str, corpo_html: str | None = None,
                     anexos: list[tuple[str, bytes]] | None = None) -> bool:
    token = _access_token(db)
    if token is None:
        return False
    cfg = config_gmail(db)

    msg = EmailMessage()
    msg["From"] = cfg.get("gmail_conta", "")
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo_texto)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")
    for nome, dados in (anexos or []):
        msg.add_attachment(dados, maintype="application", subtype="pdf", filename=nome)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = httpx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                   headers={"Authorization": f"Bearer {token}"},
                   json={"raw": raw}, timeout=30)
    if r.status_code == 200:
        log.info("E-mail Gmail API enviado para %s: %s", destinatario, assunto)
        return True
    log.error("Gmail send falhou (%s): %s", r.status_code, r.text[:300])
    return False


def desconectar(db: Session) -> None:
    gravar_config(db, {"gmail_refresh_token": "", "gmail_conta": ""})
    db.commit()
