"""Configurações pelo painel: perfil do usuário do RH e SMTP (com teste de envio)."""

import smtplib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.core.security import hash_senha, verificar_senha
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.config_dinamica import CHAVES_SMTP, gravar_config, smtp_config
from app.services.email import enviar_email, html_moderno

router = APIRouter(tags=["configuracoes"])


# ---------- Perfil ----------


class PerfilIn(BaseModel):
    nome: str | None = None
    email: EmailStr | None = None


@router.get("/rh/me")
def meu_perfil(rh: UsuarioRH = Depends(requer_rh)) -> dict:
    return {"nome": rh.nome, "email": rh.email}


@router.put("/rh/me")
def atualizar_perfil(payload: PerfilIn, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if payload.email and payload.email.lower() != rh.email:
        existe = db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower()))
        if existe is not None:
            raise HTTPException(status_code=409, detail="email_ja_utilizado")
        rh.email = payload.email.lower()
    if payload.nome:
        rh.nome = payload.nome
    registrar(db, "perfil_atualizado", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"nome": rh.nome, "email": rh.email}


class SenhaIn(BaseModel):
    senha_atual: str
    senha_nova: str


@router.put("/rh/me/senha", status_code=204)
def trocar_senha(payload: SenhaIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    if not verificar_senha(payload.senha_atual, rh.senha_hash):
        raise HTTPException(status_code=422, detail="senha_atual_incorreta")
    if len(payload.senha_nova) < 8:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")
    rh.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "senha_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ---------- Equipe (usuários do RH) ----------


class UsuarioNovoIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str


class UsuarioEditIn(BaseModel):
    nome: str | None = None
    email: EmailStr | None = None
    ativo: bool | None = None


class UsuarioSenhaIn(BaseModel):
    senha_nova: str


def _usuario_dict(u: UsuarioRH, eu: UsuarioRH) -> dict:
    return {"id": u.id, "nome": u.nome, "email": u.email, "ativo": u.ativo,
            "criado_em": u.criado_em, "sou_eu": u.id == eu.id}


@router.get("/rh/usuarios")
def listar_usuarios(db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> list[dict]:
    usuarios = db.scalars(select(UsuarioRH).order_by(UsuarioRH.criado_em)).all()
    return [_usuario_dict(u, rh) for u in usuarios]


@router.post("/rh/usuarios", status_code=201)
def criar_usuario(payload: UsuarioNovoIn, request: Request, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if len(payload.senha) < 8:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")
    email = payload.email.lower()
    if db.scalar(select(UsuarioRH).where(UsuarioRH.email == email)) is not None:
        raise HTTPException(status_code=409, detail="email_ja_utilizado")
    novo = UsuarioRH(nome=nome, email=email, senha_hash=hash_senha(payload.senha))
    db.add(novo)
    registrar(db, "usuario_rh_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"novo_usuario": email})
    db.commit()

    email_enviado = True
    base = base_url_publica(request)
    try:
        enviar_email(
            email,
            "🌱 Green House — seu acesso ao Portal de Admissão",
            f"Olá, {nome.split()[0].title()}!\n\n"
            f"{rh.nome} criou um acesso para você no painel do RH do Portal de Admissão.\n"
            f"Acesse {base}/rh com o e-mail {email} e a senha "
            "que ela(e) vai lhe informar.\n\n"
            "IMPORTANTE: troque a senha no primeiro acesso, em Configurações → Senha.\n",
            html_moderno(
                "Seu acesso ao painel do RH",
                [
                    f"Olá, <strong>{nome.split()[0].title()}</strong>!",
                    f"<strong>{rh.nome}</strong> criou um acesso para você no painel do RH "
                    "do Portal de Admissão da Green House.",
                    f"Entre em <a href='{base}/rh'>"
                    f"{base}/rh</a> com o e-mail <strong>{email}</strong> "
                    "e a senha que quem criou o acesso vai lhe informar.",
                    "<strong>Troque a senha no primeiro acesso</strong>, em "
                    "Configurações → Senha.",
                ],
            ),
            levantar_erro=True,
        )
    except Exception:
        email_enviado = False
    return {**_usuario_dict(novo, rh), "email_enviado": email_enviado}


@router.put("/rh/usuarios/{usuario_id}")
def editar_usuario(usuario_id: uuid.UUID, payload: UsuarioEditIn,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    usuario = db.get(UsuarioRH, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario_nao_encontrado")
    if payload.ativo is False:
        if usuario.id == rh.id:
            raise HTTPException(status_code=422, detail="nao_pode_desativar_a_si_mesmo")
        ativos = db.scalars(select(UsuarioRH).where(UsuarioRH.ativo == True)).all()  # noqa: E712
        if len([u for u in ativos if u.id != usuario.id]) == 0:
            raise HTTPException(status_code=422, detail="ultimo_usuario_ativo")
    if payload.email and payload.email.lower() != usuario.email:
        if db.scalar(select(UsuarioRH).where(UsuarioRH.email == payload.email.lower())):
            raise HTTPException(status_code=409, detail="email_ja_utilizado")
        usuario.email = payload.email.lower()
    if payload.nome is not None and payload.nome.strip():
        usuario.nome = payload.nome.strip()
    if payload.ativo is not None:
        usuario.ativo = payload.ativo
    registrar(db, "usuario_rh_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"usuario": usuario.email, "ativo": usuario.ativo})
    db.commit()
    return _usuario_dict(usuario, rh)


@router.put("/rh/usuarios/{usuario_id}/senha", status_code=204)
def redefinir_senha_usuario(usuario_id: uuid.UUID, payload: UsuarioSenhaIn,
                            db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(requer_rh)) -> None:
    usuario = db.get(UsuarioRH, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario_nao_encontrado")
    if len(payload.senha_nova) < 8:
        raise HTTPException(status_code=422, detail="senha_curta_minimo_8")
    usuario.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "usuario_rh_senha_redefinida", ator="rh", ator_detalhe=rh.email,
              detalhe={"usuario": usuario.email})
    db.commit()


# ---------- Assinantes dos documentos oficiais ----------


class AssinantesIn(BaseModel):
    ass1_nome: str
    ass1_cargo: str
    ass1_cpf: str
    ass2_nome: str
    ass2_cargo: str
    ass2_cpf: str


@router.get("/rh/config/assinantes")
def ver_assinantes(db: Session = Depends(get_db),
                   _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.services.fichas import assinantes_config
    a1, a2 = assinantes_config(db)
    return {"ass1_nome": a1[0], "ass1_cargo": a1[1], "ass1_cpf": a1[2],
            "ass2_nome": a2[0], "ass2_cargo": a2[1], "ass2_cpf": a2[2]}


@router.put("/rh/config/assinantes")
def salvar_assinantes(payload: AssinantesIn, db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    gravar_config(db, {
        "doc_ass1_nome": payload.ass1_nome.strip(),
        "doc_ass1_cargo": payload.ass1_cargo.strip(),
        "doc_ass1_cpf": payload.ass1_cpf.strip(),
        "doc_ass2_nome": payload.ass2_nome.strip(),
        "doc_ass2_cargo": payload.ass2_cargo.strip(),
        "doc_ass2_cpf": payload.ass2_cpf.strip(),
    })
    registrar(db, "assinantes_alterados", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_assinantes(db, rh)


# ---------- SMTP ----------


class SmtpIn(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str | None = None  # None = manter a senha atual
    smtp_from: EmailStr


class OcrIn(BaseModel):
    mistral_api_key: str | None = None
    # Só ligue DEPOIS de a Mistral aprovar o Zero Data Retention no plano Scale:
    # controla se a leitura por IA pode tocar documento de SAÚDE (atestado).
    zdr_ativo: bool | None = None


@router.get("/rh/config/ocr")
def ver_ocr(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.services.ocr_ia import chave_mistral
    from app.services.ocr_roteador import zdr_ativo
    return {"chave_definida": bool(chave_mistral(db)),
            "zdr_ativo": zdr_ativo(db)}


@router.put("/rh/config/ocr")
def salvar_ocr(payload: OcrIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Chave da Mistral para o OCR com IA. Chave vazia desliga (volta ao OCR
    local). A chave nunca aparece em log nem volta na resposta.

    `zdr_ativo` é a trava do documento de SAÚDE: só deve ser ligado depois que a
    Mistral aprovar o Zero Data Retention no plano Scale — enquanto desligado,
    atestado de saúde não é enviado para a IA (fica só no MinIO, o RH digita à
    mão). Guardado como "1"/"" na config, que é o que o `ocr_roteador` lê."""
    from app.services.ocr_roteador import CHAVE_ZDR
    if payload.mistral_api_key is not None:
        gravar_config(db, {"mistral_api_key": (payload.mistral_api_key or "").strip()})
        registrar(db, "ocr_ia_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"ativado": bool((payload.mistral_api_key or "").strip())})
    if payload.zdr_ativo is not None:
        gravar_config(db, {CHAVE_ZDR: "1" if payload.zdr_ativo else ""})
        registrar(db, "ocr_zdr_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"ativo": payload.zdr_ativo})
    db.commit()
    return ver_ocr(db, rh)


@router.post("/rh/config/ocr/testar")
def testar_ocr(db: Session = Depends(get_db),
               _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.services.ocr_ia import chave_mistral, testar_mistral
    chave = chave_mistral(db)
    if not chave:
        raise HTTPException(status_code=422, detail="chave_nao_configurada")
    try:
        texto = testar_mistral(chave)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "texto_lido": texto[:120]}


@router.get("/rh/config/smtp")
def ver_smtp(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cfg = smtp_config(db)
    return {
        "smtp_host": cfg["host"], "smtp_port": cfg["port"], "smtp_user": cfg["user"],
        "smtp_from": cfg["from_"], "senha_definida": bool(cfg["password"]),
    }


@router.put("/rh/config/smtp")
def salvar_smtp(payload: SmtpIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    valores = {
        "smtp_host": payload.smtp_host.strip(),
        "smtp_port": str(payload.smtp_port),
        "smtp_user": payload.smtp_user.strip(),
        "smtp_from": str(payload.smtp_from),
    }
    if payload.smtp_password:
        valores["smtp_password"] = payload.smtp_password
    gravar_config(db, valores)
    registrar(db, "smtp_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"host": valores["smtp_host"], "user": valores["smtp_user"]})
    db.commit()
    return ver_smtp(db, rh)


@router.post("/rh/config/smtp/testar")
def testar_smtp(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    try:
        enviar_email(
            rh.email, "✅ Teste de e-mail — Portal de Admissão Green House",
            "Se você recebeu esta mensagem, o SMTP do Portal de Admissão está funcionando.",
            levantar_erro=True,
        )
    except RuntimeError:
        raise HTTPException(status_code=422, detail="smtp_nao_configurado")
    except smtplib.SMTPAuthenticationError as exc:
        servidor = exc.smtp_error.decode(errors="replace") if isinstance(exc.smtp_error, bytes) \
            else str(exc.smtp_error)
        dica = ("O servidor recusou a autenticação. Resposta exata dele: "
                f"[{exc.smtp_code}] {servidor} — ")
        if "SmtpClientAuthentication is disabled for the Tenant" in servidor:
            dica += ("o SMTP autenticado está DESLIGADO PARA A ORGANIZAÇÃO inteira: o admin "
                     "precisa habilitar em admin.exchange.microsoft.com → Configurações → "
                     "Fluxo de emails → 'Desativar o protocolo SMTP AUTH' (desmarcar), ou "
                     "habilitar só para a caixa e aguardar até 1h.")
        elif "SmtpClientAuthentication is disabled for the Mailbox" in servidor:
            dica += ("o SMTP autenticado está desligado PARA ESTA CAIXA: Exchange admin → "
                     "caixa de correio → Email apps → marcar 'SMTP autenticado' "
                     "(propaga em até 1h).")
        elif "basic authentication is disabled" in servidor.lower():
            dica += ("a autenticação básica está bloqueada no tenant (Security defaults). "
                     "Alternativas: senha de aplicativo com MFA, ou conectar via OAuth "
                     "quando houver domínio com HTTPS.")
        else:
            dica += ("confira usuário/senha. Com MFA ativado, a senha normal NÃO funciona — "
                     "use uma senha de aplicativo (mysignins.microsoft.com/security-info).")
        raise HTTPException(status_code=422, detail=dica) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"falha_no_envio: {exc}") from exc
    registrar(db, "smtp_teste_ok", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"enviado_para": rh.email}


# ---------- Microsoft 365 (OAuth + Graph) ----------

from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings
from app.services import m365
from app.services.config_dinamica import gravar_config


def _state_serializer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt="m365-oauth")


def _redirect_uri(request: Request) -> str:
    """Derivado da requisição: em localhost mostra localhost, na VPS mostra
    IP:porta ou domínio — e o texto de instrução do painel acompanha."""
    return f"{base_url_publica(request)}/api/rh/config/m365/callback"


class M365In(BaseModel):
    client_id: str
    tenant_id: str
    client_secret: str | None = None  # None = manter


@router.get("/rh/config/m365")
def ver_m365(request: Request, db: Session = Depends(get_db),
             _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cfg = m365.config_m365(db)
    return {
        "client_id": cfg.get("m365_client_id", ""),
        "tenant_id": cfg.get("m365_tenant_id", ""),
        "secret_definido": bool(cfg.get("m365_client_secret")),
        "conectado": bool(cfg.get("m365_refresh_token")),
        "conta": cfg.get("m365_conta", ""),
        "redirect_uri": _redirect_uri(request),
    }


@router.put("/rh/config/m365")
def salvar_m365(payload: M365In, request: Request, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    valores = {"m365_client_id": payload.client_id.strip(),
               "m365_tenant_id": payload.tenant_id.strip()}
    if payload.client_secret:
        valores["m365_client_secret"] = payload.client_secret.strip()
    gravar_config(db, valores)
    registrar(db, "m365_config_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_m365(request, db, rh)


@router.get("/rh/config/m365/url-login")
def m365_url_login(request: Request, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """URL de autorização com state assinado — o front abre em popup."""
    cfg = m365.config_m365(db)
    if not cfg.get("m365_client_id"):
        raise HTTPException(status_code=422, detail="configure_client_id_primeiro")
    state = _state_serializer().dumps({"rh": str(rh.id)})
    return {"url": m365.url_autorizacao(db, _redirect_uri(request), state)}


@router.get("/rh/config/m365/callback")
def m365_callback(request: Request, db: Session = Depends(get_db)):
    """Retorno do login Microsoft (sem bearer: valida o state assinado)."""
    state = request.query_params.get("state", "")
    try:
        _state_serializer().loads(state, max_age=600)
    except BadSignature:
        return HTMLResponse("<h3>Sessão de conexão inválida ou expirada. Tente de novo.</h3>",
                            status_code=400)
    erro = request.query_params.get("error")
    if erro:
        desc = request.query_params.get("error_description", "")
        return HTMLResponse(f"<h3>Microsoft recusou: {erro}</h3><p>{desc}</p>", status_code=400)
    codigo = request.query_params.get("code", "")
    try:
        conta = m365.trocar_codigo(db, codigo, _redirect_uri(request))
    except Exception as exc:
        return HTMLResponse(f"<h3>Falha ao concluir a conexão.</h3><p>{exc}</p>", status_code=400)
    registrar(db, "m365_conectado", ator="rh", detalhe={"conta": conta})
    db.commit()
    return HTMLResponse(
        f"<div style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
        f"<h2>✅ Conta conectada: {conta}</h2>"
        f"<p>Pode fechar esta janela e voltar ao painel.</p>"
        f"<script>setTimeout(()=>window.close(),2500)</script></div>"
    )


@router.post("/rh/config/m365/desconectar", status_code=204)
def m365_desconectar(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> None:
    m365.desconectar(db)
    registrar(db, "m365_desconectado", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ---------- Google (OAuth + Gmail API) ----------

from app.services import gmail


def _state_serializer_gmail():
    return URLSafeTimedSerializer(get_settings().secret_key, salt="gmail-oauth")


def _redirect_uri_gmail(request: Request) -> str:
    return f"{base_url_publica(request)}/api/rh/config/gmail/callback"


class GmailIn(BaseModel):
    client_id: str
    client_secret: str | None = None  # None = manter


@router.get("/rh/config/gmail")
def ver_gmail(request: Request, db: Session = Depends(get_db),
              _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cfg = gmail.config_gmail(db)
    return {
        "client_id": cfg.get("gmail_client_id", ""),
        "secret_definido": bool(cfg.get("gmail_client_secret")),
        "conectado": bool(cfg.get("gmail_refresh_token")),
        "conta": cfg.get("gmail_conta", ""),
        "redirect_uri": _redirect_uri_gmail(request),
    }


@router.put("/rh/config/gmail")
def salvar_gmail(payload: GmailIn, request: Request, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    valores = {"gmail_client_id": payload.client_id.strip()}
    if payload.client_secret:
        valores["gmail_client_secret"] = payload.client_secret.strip()
    gravar_config(db, valores)
    registrar(db, "gmail_config_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_gmail(request, db, rh)


@router.get("/rh/config/gmail/url-login")
def gmail_url_login(request: Request, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """URL de autorização com state assinado — o front abre em popup."""
    cfg = gmail.config_gmail(db)
    if not cfg.get("gmail_client_id"):
        raise HTTPException(status_code=422, detail="configure_client_id_primeiro")
    state = _state_serializer_gmail().dumps({"rh": str(rh.id)})
    return {"url": gmail.url_autorizacao(db, _redirect_uri_gmail(request), state)}


@router.get("/rh/config/gmail/callback")
def gmail_callback(request: Request, db: Session = Depends(get_db)):
    """Retorno do login Google (sem bearer: valida o state assinado)."""
    state = request.query_params.get("state", "")
    try:
        _state_serializer_gmail().loads(state, max_age=600)
    except BadSignature:
        return HTMLResponse("<h3>Sessão de conexão inválida ou expirada. Tente de novo.</h3>",
                            status_code=400)
    erro = request.query_params.get("error")
    if erro:
        return HTMLResponse(f"<h3>Google recusou: {erro}</h3>", status_code=400)
    codigo = request.query_params.get("code", "")
    try:
        conta = gmail.trocar_codigo(db, codigo, _redirect_uri_gmail(request))
    except Exception as exc:
        return HTMLResponse(f"<h3>Falha ao concluir a conexão.</h3><p>{exc}</p>", status_code=400)
    registrar(db, "gmail_conectado", ator="rh", detalhe={"conta": conta})
    db.commit()
    return HTMLResponse(
        f"<div style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
        f"<h2>✅ Conta conectada: {conta}</h2>"
        f"<p>Pode fechar esta janela e voltar ao painel.</p>"
        f"<script>setTimeout(()=>window.close(),2500)</script></div>"
    )


@router.post("/rh/config/gmail/desconectar", status_code=204)
def gmail_desconectar(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> None:
    gmail.desconectar(db)
    registrar(db, "gmail_desconectado", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ---------- Webhook (Power Automate / fluxo HTTP) ----------

from app.services import webhook_email


class WebhookIn(BaseModel):
    webhook_url: str | None = None  # vazio = desliga


def _mascara_url(url: str) -> str:
    """Mostra só o começo e o fim da URL (ela contém uma assinatura secreta)."""
    if not url:
        return ""
    if len(url) <= 40:
        return url[:12] + "…"
    return url[:40] + "…" + url[-8:]


@router.get("/rh/config/webhook")
def ver_webhook(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    url = webhook_email.url_webhook(db)
    return {"configurado": bool(url), "url_mascarada": _mascara_url(url)}


@router.put("/rh/config/webhook")
def salvar_webhook(payload: WebhookIn, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    url = (payload.webhook_url or "").strip()
    if url and not url.lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="url_precisa_ser_https")
    gravar_config(db, {"webhook_email_url": url})
    registrar(db, "webhook_email_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"ativado": bool(url)})
    db.commit()
    return ver_webhook(db, rh)


@router.post("/rh/config/webhook/testar")
def testar_webhook(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not webhook_email.url_webhook(db):
        raise HTTPException(status_code=422, detail="webhook_nao_configurado")
    ok = webhook_email.enviar_via_webhook(
        db, rh.email, "✅ Teste de e-mail — Portal de Admissão Green House",
        "Se você recebeu esta mensagem, o fluxo do Power Automate está funcionando.",
        html_moderno("Fluxo do Power Automate funcionando",
                     ["Se você recebeu esta mensagem, o envio de e-mails pelo fluxo do "
                      "Power Automate está configurado corretamente."]),
    )
    if not ok:
        raise HTTPException(status_code=422, detail="falha_no_envio_pelo_fluxo")
    registrar(db, "webhook_email_teste_ok", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"enviado_para": rh.email}


# ---------- E-mail de avisos internos (ex.: "Dossiê pronto") ----------


class AvisosIn(BaseModel):
    email_avisos_internos: str | None = None
    # {chave_evento: {"emails": [...], "ativo": bool}} — None não mexe na matriz
    matriz: dict | None = None


@router.get("/rh/config/avisos")
def ver_avisos(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Avisos internos: o e-mail padrão + a MATRIZ evento × destinatários
    (v1.82). O padrão continua valendo para todo evento sem lista própria."""
    from app.services.config_dinamica import ler_config
    from app.services.notificacoes import EVENTOS, ler_matriz
    cfg = ler_config(db, ("email_avisos_internos",))
    return {"email_avisos_internos": cfg.get("email_avisos_internos", ""),
            "padrao": smtp_config(db)["from_"],
            "eventos": EVENTOS,
            "matriz": ler_matriz(db)}


@router.put("/rh/config/avisos")
def salvar_avisos(payload: AvisosIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    from app.services.notificacoes import gravar_matriz
    email = (payload.email_avisos_internos or "").strip()
    if email and "@" not in email:
        raise HTTPException(status_code=422, detail="email_invalido")
    gravar_config(db, {"email_avisos_internos": email})
    detalhe = {"destino": email or "(padrão: remetente)"}
    # `matriz` ausente = chamada antiga, só mexe no padrão (não zera a matriz)
    if payload.matriz is not None:
        limpa = gravar_matriz(db, payload.matriz)
        detalhe["eventos"] = {k: {"destinos": len(v["emails"]), "ativo": v["ativo"]}
                              for k, v in limpa.items()}
    registrar(db, "email_avisos_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe=detalhe)
    db.commit()
    return ver_avisos(db, rh)


# ---------- Microsoft Teams (webhook + template) ----------

from app.services import teams


class TeamsIn(BaseModel):
    webhook_url: str | None = None  # None = não mexe; "" = desliga
    template: str | None = None


@router.get("/rh/config/teams")
def ver_teams(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    url = teams.url_teams(db)
    return {"configurado": bool(url), "url_mascarada": _mascara_url(url),
            "template": teams.template_teams(db)}


@router.put("/rh/config/teams")
def salvar_teams(payload: TeamsIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    url = payload.webhook_url
    if url and not url.strip().lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="url_precisa_ser_https")
    teams.salvar_config(db, url, payload.template)
    registrar(db, "teams_config_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"configurado": bool(teams.url_teams(db))})
    db.commit()
    return ver_teams(db, rh)


@router.post("/rh/config/teams/testar")
def testar_teams(db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not teams.url_teams(db):
        raise HTTPException(status_code=422, detail="teams_nao_configurado")
    if not teams.enviar_mensagem(
            db, "✅ Teste do Portal de Admissão Green House — se você está vendo esta "
                "mensagem, o webhook do Teams está funcionando."):
        raise HTTPException(status_code=422, detail="falha_no_envio_ao_teams")
    registrar(db, "teams_teste_ok", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"ok": True}


# ---------- Auditoria ----------


@router.get("/rh/auditoria")
def auditoria(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(requer_rh),
              limite: int = 200) -> list[dict]:
    from app.models.evento import EventoAuditoria

    eventos = db.scalars(
        select(EventoAuditoria).order_by(EventoAuditoria.criado_em.desc()).limit(min(limite, 500))
    ).all()
    return [
        {"quando": e.criado_em, "acao": e.acao, "ator": e.ator, "ator_detalhe": e.ator_detalhe,
         "candidato_id": e.candidato_id, "detalhe": e.detalhe}
        for e in eventos
    ]
