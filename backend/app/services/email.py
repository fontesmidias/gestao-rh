"""Envio de e-mails via SMTP (.env). Falha de e-mail nunca derruba a operação principal:
quem chama decide se loga e segue (convite tem o link na resposta como fallback)."""

import logging
import smtplib
from email.message import EmailMessage

from app.core.db import SessionLocal

log = logging.getLogger(__name__)


def enviar_email(destinatario: str, assunto: str, corpo_texto: str, corpo_html: str | None = None,
                 levantar_erro: bool = False,
                 anexos: list[tuple[str, bytes]] | None = None) -> bool:
    """anexos: lista de (nome_do_arquivo.pdf, bytes)."""
    from app.services.config_dinamica import smtp_config
    from app.services.m365 import config_m365, enviar_via_graph

    # Microsoft 365 conectado tem prioridade sobre SMTP.
    with SessionLocal() as db:
        if config_m365(db).get("m365_refresh_token"):
            ok = enviar_via_graph(db, destinatario, assunto, corpo_texto, corpo_html, anexos)
            if ok:
                return True
            if levantar_erro:
                raise RuntimeError("falha_envio_m365: reconecte a conta em Configurações")
            return False
        cfg = smtp_config(db)

    if not cfg["host"] or "seuprovedor" in cfg["host"]:
        log.warning("SMTP não configurado; e-mail para %s não enviado.", destinatario)
        if levantar_erro:
            raise RuntimeError("smtp_nao_configurado")
        return False

    msg = EmailMessage()
    msg["From"] = cfg["from_"]
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.set_content(corpo_texto)
    if corpo_html:
        msg.add_alternative(corpo_html, subtype="html")
    for nome, dados in (anexos or []):
        msg.add_attachment(dados, maintype="application", subtype="pdf", filename=nome)

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


def email_convite(nome: str, link: str) -> tuple[str, str, str]:
    """(assunto, texto, html) do convite de admissão com o link mágico."""
    primeiro_nome = nome.split()[0].title() if nome.strip() else "candidato(a)"
    assunto = "🌱 Green House — comece sua admissão"
    texto = (
        f"Olá, {primeiro_nome}!\n\n"
        "Seja bem-vindo(a) à Green House! Para concluir sua admissão, acesse o link abaixo "
        "pelo celular ou computador. Não precisa de senha — é só tocar e começar:\n\n"
        f"{link}\n\n"
        "IMPORTANTE: comece AGORA. Sua contratação só é efetivada depois que você preencher "
        "os dados, assinar os documentos e enviar toda a documentação. Se precisar "
        "interromper, tudo fica salvo — mas conclua o quanto antes: sem a documentação "
        "completa, o RH não pode efetivar seu registro.\n\n"
        "Qualquer dúvida, fale com o RH.\n"
    )
    html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:560px;margin:auto;
                padding:24px;color:#1f2430">
      <h2 style="color:#2b2e4a">🌱 Bem-vindo(a) à Green House!</h2>
      <p>Olá, <strong>{primeiro_nome}</strong>!</p>
      <p>Para concluir sua admissão, toque no botão abaixo. <strong>Não precisa de senha.</strong></p>
      <p style="text-align:center;margin:32px 0">
        <a href="{link}" style="background:#8cc63f;color:#fff;text-decoration:none;
           padding:14px 28px;border-radius:8px;font-weight:bold">Começar minha admissão</a>
      </p>
      <p><strong>Comece agora:</strong> sua contratação só é efetivada depois do envio
         completo dos dados, assinaturas e documentos. Tudo fica salvo se precisar
         interromper — mas <strong>conclua o quanto antes</strong>.</p>
      <p style="color:#667">Se o botão não funcionar, copie este endereço:<br>
         <a href="{link}">{link}</a></p>
    </div>
    """
    return assunto, texto, html
