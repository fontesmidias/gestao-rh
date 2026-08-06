"""Envio de e-mails via SMTP (.env). Falha de e-mail nunca derruba a operação principal:
quem chama decide se loga e segue (convite tem o link na resposta como fallback)."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.db import SessionLocal

log = logging.getLogger(__name__)
# Canal próprio para o que se pergunta com mais frequência num incidente: "o
# e-mail saiu?". Fica no MESMO arquivo dos demais logs — o nome do logger é o
# que permite filtrar por "email" na tela (v2.41).
log_email = logging.getLogger("email.envio")


def _tipo_do_anexo(nome: str) -> tuple[str, str]:
    """MIME do anexo pela EXTENSÃO.

    Antes todo anexo saía como `application/pdf`, chumbado — inclusive o `.txt`
    do log enviado 4x por dia, que chegava ao Bruno como um PDF corrompido e
    não abria de jeito nenhum (relato de 2026-08-01). O arquivo estava
    perfeito; o envelope é que mentia sobre ele.
    """
    import mimetypes

    tipo, _ = mimetypes.guess_type(nome or "")
    if not tipo:
        # `.md` não está no mapa de todo sistema, e é o formato do resumo de
        # log — sem esta linha ele voltaria a ser octet-stream.
        if (nome or "").lower().endswith(".md"):
            return "text", "markdown"
        return "application", "octet-stream"
    principal, _, secundario = tipo.partition("/")
    return principal, secundario or "octet-stream"


def enviar_email(destinatario: str, assunto: str, corpo_texto: str, corpo_html: str | None = None,
                 levantar_erro: bool = False,
                 anexos: list[tuple[str, bytes]] | None = None,
                 remetente: str | None = None) -> bool:
    """Envia e REGISTRA o resultado — saiu, por onde, e por que não saiu.

    O registro existe porque "o e-mail não chegou" é a pergunta mais frequente
    em qualquer incidente daqui, e a resposta estava espalhada: cada provedor
    logava à sua maneira e o retorno era descartado em vários call-sites (foi
    o que escondeu o caso dos códigos do creche). Agora há **uma linha por
    envio**, no canal `email.envio`, com destinatário, assunto e desfecho.

    Nunca levanta por causa do log: o envelope não pode derrubar a carta.
    """
    import time as _t

    inicio = _t.perf_counter()
    ok = False
    try:
        ok = _enviar_email(destinatario, assunto, corpo_texto, corpo_html,
                           levantar_erro, anexos, remetente)
        return ok
    finally:
        try:
            ms = round((_t.perf_counter() - inicio) * 1000)
            log_email.log(
                logging.INFO if ok else logging.WARNING,
                "envio=%s destino=%s assunto=%r anexos=%d ms=%s",
                "ok" if ok else "FALHOU", destinatario or "(sem destinatário)",
                (assunto or "")[:80], len(anexos or []), ms,
            )
        except Exception:  # log nunca atrapalha o envio
            pass


def _enviar_email(destinatario: str, assunto: str, corpo_texto: str, corpo_html: str | None = None,
                  levantar_erro: bool = False,
                  anexos: list[tuple[str, bytes]] | None = None,
                  remetente: str | None = None) -> bool:
    """anexos: lista de (nome_do_arquivo.pdf, bytes).

    `remetente` (v2.67) sobrepõe o `From` **no caminho SMTP**, e só nele. É
    honesto dizer o limite: nos caminhos M365, Google e webhook a mensagem sai
    da CAIXA CONECTADA por construção — o Graph recusa `From` de terceiro sem
    permissão de aplicação (`SendAs`), e forjar o cabeçalho ali resultaria em
    e-mail rejeitado ou marcado como spam, que é pior do que sair do endereço
    de sempre. Nesses casos o remetente pedido é ignorado em vez de derrubar o
    envio: o convite de entrevista sair do endereço padrão é um detalhe de
    apresentação; não sair é uma entrevista perdida.
    """
    if not destinatario:
        # Candidato cadastrado sem e-mail (convite copiado para o WhatsApp):
        # não há para onde enviar — quem chama trata email_enviado=False.
        log.info("Sem destinatário para '%s'; e-mail não enviado.", assunto)
        return False
    from app.services.config_dinamica import smtp_config
    from app.services.gmail import config_gmail, enviar_via_gmail
    from app.services.m365 import config_m365, enviar_via_graph
    from app.services.webhook_email import enviar_via_webhook, url_webhook

    # Prioridade: Microsoft 365 → Google → Webhook (Power Automate) → SMTP.
    with SessionLocal() as db:
        if config_m365(db).get("m365_refresh_token"):
            ok = enviar_via_graph(db, destinatario, assunto, corpo_texto, corpo_html, anexos)
            if ok:
                return True
            if levantar_erro:
                raise RuntimeError("falha_envio_m365: reconecte a conta em Configurações")
            return False
        if config_gmail(db).get("gmail_refresh_token"):
            ok = enviar_via_gmail(db, destinatario, assunto, corpo_texto, corpo_html, anexos)
            if ok:
                return True
            if levantar_erro:
                raise RuntimeError("falha_envio_google: reconecte a conta em Configurações")
            return False
        if url_webhook(db):
            ok = enviar_via_webhook(db, destinatario, assunto, corpo_texto, corpo_html, anexos)
            if ok:
                return True
            if levantar_erro:
                raise RuntimeError("falha_envio_webhook: confira a URL do fluxo no Power Automate")
            return False
        cfg = smtp_config(db)

    if not cfg["host"] or "seuprovedor" in cfg["host"]:
        log.warning("SMTP não configurado; e-mail para %s não enviado.", destinatario)
        if levantar_erro:
            raise RuntimeError("smtp_nao_configurado")
        return False

    msg = EmailMessage()
    msg["From"] = (remetente or "").strip() or cfg["from_"]
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo_texto)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")
    for nome, dados in (anexos or []):
        maintype, subtype = _tipo_do_anexo(nome)
        msg.add_attachment(dados, maintype=maintype, subtype=subtype, filename=nome)

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as smtp:
            smtp.starttls()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
        log.info("E-mail enviado para %s: %s", destinatario, assunto)
        return True
    except Exception:
        log.exception("Falha ao enviar e-mail para %s", destinatario)
        if levantar_erro:
            raise
        return False


def html_moderno(titulo: str, paragrafos: list[str], destaque: str | None = None,
                 botao_texto: str | None = None, botao_url: str | None = None,
                 rodape: str = "RH — Green House") -> str:
    """Template HTML padrão dos e-mails: card branco arredondado sobre fundo suave,
    faixa de gradiente, código em caixa de destaque e botão de ação."""
    corpo = "".join(
        f'<p style="margin:0 0 14px;color:#3a4152;font-size:15px;line-height:1.6">{p}</p>'
        for p in paragrafos
    )
    bloco_destaque = (
        f'<div style="text-align:center;margin:26px 0">'
        f'<span style="display:inline-block;background:#f2f8ea;border:2px dashed #8cc63f;'
        f'border-radius:14px;padding:16px 34px;font-size:32px;letter-spacing:10px;'
        f'font-weight:700;color:#2b2e4a;font-family:Consolas,monospace">{destaque}</span></div>'
        if destaque else ""
    )
    bloco_botao = (
        f'<div style="text-align:center;margin:28px 0 10px">'
        f'<a href="{botao_url}" style="background:linear-gradient(135deg,#8cc63f,#4f9d3a);'
        f'color:#fff;text-decoration:none;padding:15px 36px;border-radius:12px;'
        f'font-weight:700;font-size:16px;display:inline-block;'
        f'box-shadow:0 4px 14px rgba(79,157,58,.35)">{botao_texto}</a></div>'
        if botao_texto and botao_url else ""
    )
    return f"""
    <div style="background:#eef3ea;padding:32px 12px;font-family:'Segoe UI',system-ui,Roboto,sans-serif">
      <div style="max-width:560px;margin:auto;background:#ffffff;border-radius:18px;
                  overflow:hidden;box-shadow:0 8px 30px rgba(43,46,74,.12)">
        <div style="height:6px;background:linear-gradient(90deg,#8cc63f,#4f9d3a,#2b2e4a)"></div>
        <div style="padding:30px 34px 26px">
          <p style="margin:0 0 6px;font-size:13px;font-weight:700;letter-spacing:2px;
                    color:#8cc63f;text-transform:uppercase">🌱 Green House</p>
          <h2 style="margin:0 0 18px;color:#2b2e4a;font-size:21px">{titulo}</h2>
          {corpo}{bloco_destaque}{bloco_botao}
        </div>
        <div style="background:#f7faf4;padding:14px 34px;color:#8a93a3;font-size:12px">
          {rodape} · mensagem automática do Portal de Admissão
        </div>
      </div>
    </div>"""

