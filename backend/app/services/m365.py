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


# Assinaturas com que o Graph recusa um `From` de terceiro. São de PERMISSÃO —
# permanentes, resolvem-se no admin do M365 liberando `Send As`, e NUNCA
# passam com uma nova tentativa. É o que separa este caso de uma falha de
# envio comum (caixa cheia, rede, token expirado), que é transitória.
#
# A regra é a da v2.00, na terceira variação: tratar os dois igual faria o RH
# achar que o sistema quebrou quando falta um clique no tenant.
_RECUSAS_DE_PERMISSAO = (
    "errorsendasdenied",
    "erroraccessdenied",
    "does not have permission to send",
    "not allowed to send as",
)


def recusou_por_permissao(status: int, corpo: str) -> bool:
    """O Graph recusou o `From` por FALTA DE PERMISSÃO (não por falha de envio)?

    Só olha respostas 403 e 400 — é onde o Graph devolve `ErrorSendAsDenied`.
    Um 500 ou um timeout é falha de envio: tentar de novo pode resolver, e
    reenviar da caixa conectada por causa dele esconderia um problema real.
    """
    if status not in (400, 403):
        return False
    texto = (corpo or "").lower()
    return any(marca in texto for marca in _RECUSAS_DE_PERMISSAO)


def enviar_via_graph(db: Session, destinatario: str, assunto: str,
                     corpo_texto: str, corpo_html: str | None = None,
                     anexos: list[tuple[str, bytes]] | None = None,
                     remetente: str | None = None) -> dict:
    """Envia pelo Graph. Devolve `{ok, aviso}` — nunca só um booleano.

    `remetente` (v2.68, § 16.1) é o endereço de recrutamento. O Graph só o
    aceita se o admin do M365 tiver liberado **`Send As`** daquela caixa para a
    conta conectada. Sem a liberação ele responde `ErrorSendAsDenied` e **o
    e-mail não sai**.

    Por isso o desenho tem duas tentativas e nunca desiste da carta:

    1. tenta com o remetente pedido;
    2. se a recusa for **de permissão**, reenvia da caixa conectada e devolve
       o `aviso` que a tela mostra ao RH, dizendo o que falta liberar.

    Falha que **não** é de permissão não vira segunda tentativa: reenviar por
    causa de um 500 esconderia um problema de envio de verdade atrás de um
    aviso sobre o tenant, mandando o RH mexer no lugar errado.
    """
    token = _access_token(db)
    if token is None:
        return {"ok": False, "aviso": None}
    mensagem = {
        "message": {
            "subject": assunto,
            "body": {"contentType": "HTML" if corpo_html else "Text",
                     "content": corpo_html or corpo_texto},
            "toRecipients": [{"emailAddress": {"address": destinatario}}],
            "attachments": [
                {"@odata.type": "#microsoft.graph.fileAttachment",
                 "name": nome, "contentType": _tipo_grafo(nome),
                 "contentBytes": base64.b64encode(dados).decode()}
                for nome, dados in (anexos or [])
            ],
        },
        "saveToSentItems": True,
    }
    pedido = (remetente or "").strip()
    if pedido:
        mensagem["message"]["from"] = {"emailAddress": {"address": pedido}}

    status, corpo = _postar(token, mensagem)
    if status == 202:
        log.info("E-mail M365/Graph enviado para %s: %s", destinatario, assunto)
        return {"ok": True, "aviso": None}

    if pedido and recusou_por_permissao(status, corpo):
        # Segunda tentativa, SEM o `from`: sai da caixa conectada. O e-mail
        # tem que sair — uma entrevista não se perde porque o tenant não foi
        # configurado.
        log.warning("Graph recusou o remetente %s por permissão; reenviando da "
                    "caixa conectada.", pedido)
        mensagem["message"].pop("from", None)
        status2, corpo2 = _postar(token, mensagem)
        if status2 == 202:
            return {"ok": True, "aviso": aviso_send_as(pedido, db)}
        log.error("Graph sendMail falhou também sem remetente (%s): %s",
                  status2, corpo2[:300])
        return {"ok": False, "aviso": None}

    log.error("Graph sendMail falhou (%s): %s", status, corpo[:300])
    return {"ok": False, "aviso": None}


def _postar(token: str, mensagem: dict) -> tuple[int, str]:
    """O POST ao Graph, isolado para as duas tentativas usarem o mesmo caminho.

    Erro de REDE devolve status 0: não é recusa de permissão (o `recusou_por_
    permissao` só olha 400/403), então cai como falha de envio, que é o que é.
    """
    try:
        r = httpx.post("https://graph.microsoft.com/v1.0/me/sendMail",
                       headers={"Authorization": f"Bearer {token}"},
                       json=mensagem, timeout=30)
        return r.status_code, r.text
    except Exception as exc:  # rede, DNS, timeout
        log.warning("Graph sendMail não respondeu: %s", exc)
        return 0, str(exc)


def aviso_send_as(remetente: str, db: Session | None = None) -> str:
    """O texto que a tela mostra quando o `Send As` não está liberado.

    Diz **o que resolve**, não só que deu errado — a lição da v2.17/v2.18: uma
    mensagem que não explica faz a pessoa repetir a mesma coisa (lá, reconferir
    um código certo; aqui, tentar reenviar um convite que nunca vai mudar de
    remetente sozinho).
    """
    conta = ""
    if db is not None:
        try:
            conta = (config_m365(db).get("m365_conta") or "").strip()
        except Exception:
            conta = ""
    de_quem = f" para a conta {conta}" if conta else " para a conta conectada"
    return (f"O e-mail saiu, mas do endereço de sempre — não de {remetente}. "
            f"O Microsoft 365 só permite enviar por esse endereço depois que o "
            f"administrador liberar a permissão \"Enviar como\" (Send As) do "
            f"endereço {remetente}{de_quem}, no admin do Microsoft 365. "
            f"Enquanto isso não for feito, os convites continuam saindo "
            f"normalmente pelo endereço de sempre.")


def _tipo_grafo(nome: str) -> str:
    """MIME do anexo pela EXTENSÃO, também no caminho do Graph.

    O `application/pdf` estava chumbado aqui — o mesmo defeito que a v2.41
    consertou no SMTP e que fazia o `.txt` do log chegar "corrompido". O `.ics`
    do convite de entrevista passa por este caminho: com o tipo errado, o
    Outlook mostra um anexo em vez de oferecer "adicionar à agenda".
    """
    from app.services.email import _tipo_do_anexo

    principal, secundario = _tipo_do_anexo(nome)
    return f"{principal}/{secundario}"


def desconectar(db: Session) -> None:
    gravar_config(db, {"m365_refresh_token": "", "m365_conta": ""})
    db.commit()
