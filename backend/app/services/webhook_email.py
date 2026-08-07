"""Envio de e-mail via webhook (Power Automate / fluxo HTTP).

Alternativa "plug and play" para quando o locatário do Microsoft 365 é
restritivo demais (SMTP autenticado e registro de aplicativo bloqueados pelo
admin — caso real deste tenant). Em vez de falar com o Graph, o RH cria um
fluxo no Power Automate com o gatilho "Quando uma solicitação HTTP é recebida",
adiciona a ação "Enviar um email (V2)" do Office 365 Outlook e cola a URL do
gatilho aqui. Mandamos um POST JSON e o fluxo dispara o e-mail pela conta já
conectada do próprio Power Automate — sem Entra, sem senha de aplicativo.

Contrato do JSON enviado ao fluxo (todos os campos sempre presentes):
    {
      "para": "destino@exemplo.com",
      "assunto": "...",
      "texto": "corpo em texto puro",
      "html": "<...>",            # vazio se não houver versão HTML
      "anexos": [                  # pode ser lista vazia
        # `tipo` vem da EXTENSÃO do nome, nunca chumbado:
        # "ficha.pdf" → application/pdf · "log.txt" → text/plain
        # "convite.ics" → text/calendar · "resumo.md" → text/markdown
        {"nome": "ficha.pdf", "tipo": "application/pdf", "conteudo_base64": "..."}
      ]
    }
"""

import base64
import logging

import httpx
from sqlalchemy.orm import Session

from app.services.config_dinamica import ler_config

log = logging.getLogger(__name__)

CHAVES_WEBHOOK = ("webhook_email_url",)


def config_webhook(db: Session) -> dict:
    return ler_config(db, CHAVES_WEBHOOK)


def url_webhook(db: Session) -> str:
    return (config_webhook(db).get("webhook_email_url") or "").strip()


def enviar_via_webhook(db: Session, destinatario: str, assunto: str,
                       corpo_texto: str, corpo_html: str | None = None,
                       anexos: list[tuple[str, bytes]] | None = None) -> bool:
    # Import LOCAL, como o `m365.py` faz: `email.py` importa este módulo
    # (dentro da função, na `enviar_email`), então import no topo fecharia
    # ciclo.
    from app.services.email import _tipo_do_anexo

    url = url_webhook(db)
    if not url:
        return False
    payload = {
        "para": destinatario,
        "assunto": assunto,
        "texto": corpo_texto,
        "html": corpo_html or "",
        # O tipo vem da EXTENSÃO (v2.71). Era `"application/pdf"` chumbado —
        # o mesmo defeito que a v2.41 corrigiu no SMTP e a v2.68 no Graph,
        # sobrevivendo no TERCEIRO caminho de envio porque nenhum teste o
        # tocava. Por aqui saem o `.txt` do log (4x/dia) e o `.ics` do convite
        # de entrevista: declarados como PDF, chegam "corrompidos" e não abrem,
        # com o arquivo perfeito do outro lado — é o envelope que mente.
        "anexos": [
            {"nome": nome, "tipo": "/".join(_tipo_do_anexo(nome)),
             "conteudo_base64": base64.b64encode(dados).decode()}
            for nome, dados in (anexos or [])
        ],
    }
    try:
        r = httpx.post(url, json=payload, timeout=45)
    except Exception:
        log.exception("Falha ao chamar o webhook de e-mail (Power Automate)")
        return False
    if 200 <= r.status_code < 300:
        log.info("E-mail via webhook (Power Automate) para %s: %s", destinatario, assunto)
        return True
    log.error("Webhook de e-mail falhou (%s): %s", r.status_code, r.text[:300])
    return False
