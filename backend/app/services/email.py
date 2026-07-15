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
    if not destinatario:
        # Candidato cadastrado sem e-mail (convite copiado para o WhatsApp):
        # não há para onde enviar — quem chama trata email_enviado=False.
        log.info("Sem destinatário para '%s'; e-mail não enviado.", assunto)
        return False
    from app.services.config_dinamica import smtp_config
    from app.services.gmail import config_gmail, enviar_via_gmail
    from app.services.m365 import config_m365, enviar_via_graph

    # Prioridade: Microsoft 365 → Google → SMTP.
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
    html = html_moderno(
        f"Bem-vindo(a), {primeiro_nome}!",
        [
            "Para concluir a sua admissão, toque no botão abaixo. "
            "<strong>Não precisa de senha.</strong>",
            "<strong>Comece agora:</strong> sua contratação só é efetivada depois do envio "
            "completo dos dados, assinaturas e documentos. Tudo fica salvo se precisar "
            "interromper — mas <strong>conclua o quanto antes</strong>.",
            f'Se o botão não funcionar, copie este endereço: <a href="{link}">{link}</a>',
        ],
        botao_texto="Começar minha admissão",
        botao_url=link,
    )
    return assunto, texto, html
