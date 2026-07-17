"""Notificações no Microsoft Teams via webhook (Incoming Webhook do canal OU
gatilho HTTP de um fluxo do Power Automate que posta no Teams).

O RH cola a URL do webhook e escreve um template com variáveis ({{nome}},
{{cargo}}…); ao enviar, as variáveis do candidato são preenchidas e a mensagem
é postada no canal. Mesmo espírito do webhook de e-mail: nada de OAuth."""

import logging

import httpx
from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

log = logging.getLogger(__name__)

CHAVES_TEAMS = ("teams_webhook_url", "teams_template")

# Template padrão sugerido (o RH edita no painel).
TEMPLATE_PADRAO = (
    "🟢 **Nova movimentação de admissão**\n\n"
    "**Colaborador:** {{nome}}\n"
    "**Cargo:** {{cargo}}\n"
    "**Posto:** {{posto}}\n"
    "**Status:** {{status}}"
)


def config_teams(db: Session) -> dict:
    return ler_config(db, CHAVES_TEAMS)


def url_teams(db: Session) -> str:
    return (config_teams(db).get("teams_webhook_url") or "").strip()


def template_teams(db: Session) -> str:
    return config_teams(db).get("teams_template") or TEMPLATE_PADRAO


def salvar_config(db: Session, url: str | None, template: str | None) -> None:
    valores = {}
    if url is not None:
        valores["teams_webhook_url"] = url.strip()
    if template is not None:
        valores["teams_template"] = template
    if valores:
        gravar_config(db, valores)


def enviar_mensagem(db: Session, texto: str) -> bool:
    """Posta `texto` (Markdown) no canal do Teams configurado. O payload usa o
    formato de MessageCard, aceito tanto pelo Incoming Webhook do Teams quanto
    por um fluxo do Power Automate que espere {'text': ...}."""
    url = url_teams(db)
    if not url:
        return False
    payload = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": "Portal de Admissão Green House",
        "themeColor": "16C464",
        "text": texto,
    }
    try:
        r = httpx.post(url, json=payload, timeout=30)
    except Exception:
        log.exception("Falha ao chamar o webhook do Teams")
        return False
    if 200 <= r.status_code < 300:
        log.info("Mensagem enviada ao Teams")
        return True
    log.error("Webhook do Teams falhou (%s): %s", r.status_code, r.text[:300])
    return False
