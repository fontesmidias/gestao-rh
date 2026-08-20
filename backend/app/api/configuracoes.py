"""Configurações pelo painel: perfil do usuário do RH e SMTP (com teste de envio)."""

import smtplib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import exige, exigir_senha_forte, requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.core.security import hash_senha, verificar_senha
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.config_dinamica import CHAVES_SMTP, gravar_config, smtp_config
from app.services.email import enviar_email, html_moderno
from app.services.email_templates import enviar_modelo

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
    exigir_senha_forte(payload.senha_nova)
    rh.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "senha_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ---------- Equipe (usuários do RH) ----------


class UsuarioNovoIn(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    # Papel do usuário (v2.86). O padrão é `rh` — o papel operacional —, nunca
    # `superadmin`: quem cria usuário decide conscientemente promover alguém,
    # e um default permissivo faria todo cadastro apressado virar mais um dono
    # do sistema.
    papel: str = "rh"


class UsuarioEditIn(BaseModel):
    nome: str | None = None
    email: EmailStr | None = None
    ativo: bool | None = None
    papel: str | None = None


class UsuarioSenhaIn(BaseModel):
    senha_nova: str


def _usuario_dict(u: UsuarioRH, eu: UsuarioRH) -> dict:
    return {"id": u.id, "nome": u.nome, "email": u.email, "ativo": u.ativo,
            "papel": u.papel, "criado_em": u.criado_em, "sou_eu": u.id == eu.id}


def _papel_valido(db: Session, chave: str) -> str:
    """Confere que o papel existe antes de gravá-lo.

    Papel escrito errado NÃO dá erro na hora: a pessoa é criada, entra no
    sistema e simplesmente não consegue fazer nada — porque
    `permissoes_do_usuario` nega o que não resolve. O sintoma aparece longe da
    causa (403 em tudo, sem mensagem que fale de papel), então a hora de
    recusar é aqui.
    """
    from app.models.papel import Papel

    chave = (chave or "").strip().lower()
    if db.scalar(select(Papel).where(Papel.chave == chave)) is None:
        raise HTTPException(status_code=422, detail={
            "erro": "papel_desconhecido", "papel": chave})
    return chave


def _sobraria_sem_superadmin(db: Session, alvo: UsuarioRH,
                             novo_papel: str | None = None,
                             desativando: bool = False) -> bool:
    """A instalação ficaria sem NENHUM superadmin ativo depois desta mudança?

    Sem esta trava, rebaixar ou desativar o último superadmin fecha a porta por
    dentro: ninguém mais consegue gerir papéis (é `config:usuarios`, que só ele
    tem por padrão), e não há tela para desfazer — só acesso ao banco. É a
    mesma família do `ultimo_usuario_ativo` que já existia aqui, um degrau
    acima.
    """
    from app.services.permissoes import PAPEL_SUPERADMIN

    if alvo.papel != PAPEL_SUPERADMIN:
        return False  # mexer em quem não é superadmin nunca esvazia o grupo
    if not desativando and (novo_papel or alvo.papel) == PAPEL_SUPERADMIN:
        return False  # continua superadmin
    outros = db.scalars(
        select(UsuarioRH).where(UsuarioRH.papel == PAPEL_SUPERADMIN,
                                UsuarioRH.ativo.is_(True))).all()
    return len([u for u in outros if u.id != alvo.id]) == 0


@router.get("/rh/usuarios")
def listar_usuarios(db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("config:usuarios"))) -> list[dict]:
    usuarios = db.scalars(select(UsuarioRH).order_by(UsuarioRH.criado_em)).all()
    return [_usuario_dict(u, rh) for u in usuarios]


@router.post("/rh/usuarios", status_code=201)
def criar_usuario(payload: UsuarioNovoIn, request: Request, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    exigir_senha_forte(payload.senha)
    email = payload.email.lower()
    if db.scalar(select(UsuarioRH).where(UsuarioRH.email == email)) is not None:
        raise HTTPException(status_code=409, detail="email_ja_utilizado")
    papel = _papel_valido(db, payload.papel)
    novo = UsuarioRH(nome=nome, email=email, senha_hash=hash_senha(payload.senha),
                     papel=papel)
    db.add(novo)
    registrar(db, "usuario_rh_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"novo_usuario": email, "papel": papel})
    db.commit()

    email_enviado = True
    base = base_url_publica(request)
    try:
        enviar_modelo(db, "rh_usuario_criado", email, {
            "primeiro_nome": (nome or "").split()[0].title() if nome else "",
            "email": email, "quem_criou": rh.nome, "link": base,
        })
    except Exception:
        email_enviado = False
    return {**_usuario_dict(novo, rh), "email_enviado": email_enviado}


@router.put("/rh/usuarios/{usuario_id}")
def editar_usuario(usuario_id: uuid.UUID, payload: UsuarioEditIn,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    usuario = db.get(UsuarioRH, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario_nao_encontrado")
    if payload.ativo is False:
        if usuario.id == rh.id:
            raise HTTPException(status_code=422, detail="nao_pode_desativar_a_si_mesmo")
        ativos = db.scalars(select(UsuarioRH).where(UsuarioRH.ativo == True)).all()  # noqa: E712
        if len([u for u in ativos if u.id != usuario.id]) == 0:
            raise HTTPException(status_code=422, detail="ultimo_usuario_ativo")
        if _sobraria_sem_superadmin(db, usuario, desativando=True):
            raise HTTPException(status_code=422, detail="ultimo_superadmin")
    if payload.papel is not None and payload.papel != usuario.papel:
        novo_papel = _papel_valido(db, payload.papel)
        if _sobraria_sem_superadmin(db, usuario, novo_papel=novo_papel):
            # Rebaixar o último superadmin deixaria a instalação sem ninguém
            # capaz de gerir papéis — e sem tela para desfazer.
            raise HTTPException(status_code=422, detail="ultimo_superadmin")
        usuario.papel = novo_papel
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
                            rh: UsuarioRH = Depends(exige("config:usuarios"))) -> None:
    usuario = db.get(UsuarioRH, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario_nao_encontrado")
    exigir_senha_forte(payload.senha_nova)
    usuario.senha_hash = hash_senha(payload.senha_nova)
    registrar(db, "usuario_rh_senha_redefinida", ator="rh", ator_detalhe=rh.email,
              detalhe={"usuario": usuario.email})
    db.commit()


# ---------- Credenciais de automação (MCP) ----------
#
# Ficam junto de usuários porque é isso que elas são: uma forma de um usuário
# entrar. Ver `services/token_automacao.py` para o desenho e
# `docs/planejamento/13-mcp-do-portal.md` para o que a automação pode fazer.


class TokenAutomacaoIn(BaseModel):
    usuario_id: uuid.UUID
    descricao: str
    dias_validade: int | None = None      # nulo = não expira


def _token_dict(t) -> dict:
    """NUNCA devolve o segredo — ele só existe na resposta da criação."""
    return {
        "id": str(t.id), "usuario_id": str(t.usuario_id),
        "descricao": t.descricao, "prefixo": t.prefixo + "…",
        "criado_em": t.criado_em, "criado_por": t.criado_por,
        "usado_em": t.usado_em, "expira_em": t.expira_em,
        "revogado_em": t.revogado_em, "revogado_por": t.revogado_por,
        "valido": t.valido,
    }


@router.get("/rh/tokens-automacao")
def listar_tokens_automacao(db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(exige("config:usuarios"))) -> list[dict]:
    """Lista as credenciais de máquina. Mostra o prefixo e o último uso — é o
    que permite responder "qual eu revogo?" e "este ainda está em uso?" sem
    revelar segredo nenhum."""
    from app.models.token_automacao import TokenAutomacao
    tokens = db.scalars(select(TokenAutomacao).order_by(
        TokenAutomacao.criado_em.desc())).all()
    return [_token_dict(t) for t in tokens]


@router.post("/rh/tokens-automacao", status_code=201)
def criar_token_automacao(payload: TokenAutomacaoIn, db: Session = Depends(get_db),
                          rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Emite uma credencial. **O segredo aparece UMA vez, nesta resposta.**

    A tela precisa dizer isso antes de emitir: quem não copiar terá de emitir
    outra e revogar esta — que é o comportamento certo, não um incômodo a
    contornar guardando o segredo em outro lugar "por garantia".
    """
    from datetime import timedelta

    from app.services.token_automacao import emitir

    usuario = db.get(UsuarioRH, payload.usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario_nao_encontrado")
    if not usuario.ativo:
        raise HTTPException(status_code=422, detail="usuario_inativo")
    descricao = (payload.descricao or "").strip()
    if not descricao:
        # Sem descrição, "revogar o que vazou" vira adivinhação entre tokens
        # idênticos na tela.
        raise HTTPException(status_code=422, detail="descricao_obrigatoria")
    if payload.dias_validade is not None and payload.dias_validade < 1:
        raise HTTPException(status_code=422, detail="validade_invalida")

    expira = (datetime.now(timezone.utc) + timedelta(days=payload.dias_validade)
              if payload.dias_validade else None)
    registro, segredo = emitir(db, usuario, descricao, criado_por=rh.email,
                               expira_em=expira)
    # O segredo NÃO entra na auditoria — auditoria é para ser lida.
    registrar(db, "token_automacao_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"usuario": usuario.email, "descricao": descricao,
                       "prefixo": registro.prefixo, "papel": usuario.papel})
    db.commit()
    return {**_token_dict(registro), "token": segredo}


@router.delete("/rh/tokens-automacao/{token_id}", status_code=200)
def revogar_token_automacao(token_id: uuid.UUID, db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Corta o acesso na hora. **Marca, não apaga**: a linha é a prova de que a
    credencial existiu e de quando deixou de valer."""
    from app.models.token_automacao import TokenAutomacao
    from app.services.token_automacao import revogar

    registro = db.get(TokenAutomacao, token_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="token_nao_encontrado")
    ja_revogado = registro.revogado_em is not None
    revogar(db, registro, por=rh.email)
    if not ja_revogado:
        registrar(db, "token_automacao_revogado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"descricao": registro.descricao, "prefixo": registro.prefixo})
    db.commit()
    return _token_dict(registro)

# ---------- Conexões do assistente (MCP com OAuth) ----------
#
# Diferente das credenciais acima em dois pontos que importam:
#
# 1. **Ninguém emite nada aqui.** A conexão nasce quando a PESSOA faz login e
#    autoriza no Claude — não há botão de "criar". Esta tela existe para VER e
#    para CORTAR.
# 2. **Cortar é o ponto.** A pergunta que o desenho responde é "se vazar hoje à
#    noite, como eu corto?" (v2.94). Revogar aqui derruba a conexão na chamada
#    seguinte, dentro dos 10 minutos de vida do token de acesso.


def _conexao_dict(c, nome_da_pessoa: str | None, aplicativo: str | None) -> dict:
    """O que a tela mostra. NUNCA o segredo — nem o prefixo dele resolve nada.

    `papel_do_usuario` é o papel que a pessoa tinha QUANDO autorizou, guardado
    para a auditoria responder "quem era ela naquele momento?". O papel que a
    conexão concede é sempre `assistente_rh`, e é isso que `papel_concedido`
    diz — os dois juntos deixam ver que a superfície do assistente é menor que
    a da pessoa.
    """
    return {
        "id": str(c.id),
        "pessoa": nome_da_pessoa or "(usuário removido)",
        "aplicativo": aplicativo or "(aplicativo removido)",
        "papel_concedido": c.papel_concedido,
        "papel_do_usuario": c.papel_do_usuario,
        "criado_em": c.criado_em,
        "usado_em": c.usado_em,
        "expira_em": c.expira_em,
        "revogado_em": c.revogado_em,
        "revogado_por": c.revogado_por,
        "revogado_motivo": c.revogado_motivo,
        "valida": c.valido,
    }


@router.get("/rh/mcp/conexoes")
def listar_conexoes_mcp(db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(exige("config:usuarios"))) -> list[dict]:
    """As conexões do assistente, ativas e revogadas.

    Mostra as revogadas junto de propósito: a linha é a prova de que a conexão
    existiu e de quando deixou de valer, e some-la esconderia justamente o que
    se procura ao investigar.
    """
    from app.models.mcp_oauth import ClienteOAuth, Concessao

    concessoes = db.scalars(select(Concessao).order_by(
        Concessao.criado_em.desc())).all()
    if not concessoes:
        return []

    # Em LOTE, não uma consulta por linha: a lista cresce com o uso, e o N+1 do
    # dash de Talentos já custou 43 consultas para 39 registros (v2.15).
    pessoas = {u.id: u.nome for u in db.scalars(select(UsuarioRH).where(
        UsuarioRH.id.in_({c.usuario_id for c in concessoes}))).all()}
    apps = {c.id: c.client_name for c in db.scalars(select(ClienteOAuth).where(
        ClienteOAuth.id.in_({c.cliente_id for c in concessoes}))).all()}

    return [_conexao_dict(c, pessoas.get(c.usuario_id), apps.get(c.cliente_id))
            for c in concessoes]


@router.delete("/rh/mcp/conexoes/{conexao_id}", status_code=200)
def revogar_conexao_mcp(conexao_id: uuid.UUID, db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(exige("config:usuarios"))) -> dict:
    """Corta a conexão. **Marca, não apaga.**

    O efeito é imediato: o `/mcp` consulta a concessão a cada chamada, então a
    próxima já falha — não se espera o token de acesso expirar. A pessoa
    continua com o portal normal; o que cai é o assistente.
    """
    from app.models.mcp_oauth import ClienteOAuth, Concessao
    from app.services.mcp_oauth import revogar

    registro = db.get(Concessao, conexao_id)
    if registro is None:
        raise HTTPException(status_code=404, detail="conexao_nao_encontrada")
    ja_revogada = registro.revogado_em is not None
    revogar(db, registro, por=rh.email, motivo="usuario")
    if not ja_revogada:
        pessoa = db.get(UsuarioRH, registro.usuario_id)
        registrar(db, "mcp_conexao_revogada", ator="rh", ator_detalhe=rh.email,
                  detalhe={"pessoa": pessoa.email if pessoa else None,
                           "concessao": str(registro.id)})
    db.commit()
    pessoa = db.get(UsuarioRH, registro.usuario_id)
    app = db.get(ClienteOAuth, registro.cliente_id)
    return _conexao_dict(registro, pessoa.nome if pessoa else None,
                         app.client_name if app else None)



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
                   _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.fichas import assinantes_config
    a1, a2 = assinantes_config(db)
    return {"ass1_nome": a1[0], "ass1_cargo": a1[1], "ass1_cpf": a1[2],
            "ass2_nome": a2[0], "ass2_cargo": a2[1], "ass2_cpf": a2[2]}


@router.put("/rh/config/assinantes")
def salvar_assinantes(payload: AssinantesIn, db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
def ver_ocr(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.ocr_ia import chave_mistral
    from app.services.ocr_roteador import zdr_ativo
    return {"chave_definida": bool(chave_mistral(db)),
            "zdr_ativo": zdr_ativo(db)}


@router.put("/rh/config/ocr")
def salvar_ocr(payload: OcrIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
               _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.ocr_ia import chave_mistral, testar_mistral
    chave = chave_mistral(db)
    if not chave:
        raise HTTPException(status_code=422, detail="chave_nao_configurada")
    try:
        texto = testar_mistral(chave)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "texto_lido": (texto or "")[:120]}


# ---------- IA de texto: OpenRouter (principal) + Groq (reserva) ----------
# Usados pelo Minutário de mensagens e pelo Match de vagas. A cadeia tenta o
# OpenRouter primeiro e cai para a Groq se ele falhar/estourar cota — foi
# justamente uma cota estourada da Groq que derrubou 112 das 131 análises em
# 2026-07-28.


def _normalizar_modelos(bruto: str) -> str:
    """Normaliza a lista de modelos digitada no painel para uma string estável
    'a, b, c' (separadores vírgula/quebra de linha viram vírgula; espaços e itens
    vazios caem fora). String vazia mantém o override limpo → o serviço usa os
    padrões do código."""
    itens = [m.strip() for m in (bruto or "").replace("\n", ",").split(",") if m.strip()]
    return ", ".join(itens)


class GroqIn(BaseModel):
    groq_api_key: str | None = None
    groq_modelos: str | None = None


class OpenRouterIn(BaseModel):
    openrouter_api_key: str | None = None
    openrouter_modelos: str | None = None


@router.get("/rh/config/groq")
def ver_groq(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.ia_texto import (chave_groq, chave_openrouter,
                                       modelos_configurados)
    # Os MODELOS não são segredo (ao contrário da chave) — voltam ao painel para
    # o RH ver/editar a lista efetiva (a que configurou, ou os padrões).
    modelos = modelos_configurados(db)
    return {"chave_definida": bool(chave_groq(db)),
            "openrouter_definida": bool(chave_openrouter(db)),
            "openrouter_modelos": ", ".join(modelos.get("openrouter", [])),
            "groq_modelos": ", ".join(modelos.get("groq", []))}


@router.put("/rh/config/groq")
def salvar_groq(payload: GroqIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Chave da Groq (reserva da cadeia de IA). Chave vazia a desliga. A
    chave nunca aparece em log nem volta na resposta — padrão do OCR."""
    if payload.groq_api_key is not None:
        gravar_config(db, {"groq_api_key": (payload.groq_api_key or "").strip()})
        registrar(db, "groq_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"ativado": bool((payload.groq_api_key or "").strip())})
    if payload.groq_modelos is not None:
        # Lista vazia limpa o override (volta aos padrões do código). O valor não
        # é segredo — pode ir para a auditoria.
        modelos = _normalizar_modelos(payload.groq_modelos)
        gravar_config(db, {"groq_modelos": modelos})
        registrar(db, "groq_modelos_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"modelos": modelos})
    db.commit()
    return ver_groq(db, rh)


@router.post("/rh/config/groq/testar")
def testar_groq_rota(db: Session = Depends(get_db),
                     _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.ia_texto import chave_groq, testar_groq
    chave = chave_groq(db)
    if not chave:
        raise HTTPException(status_code=422, detail="chave_nao_configurada")
    try:
        texto = testar_groq(chave)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "texto_lido": (texto or "")[:120]}


@router.put("/rh/config/openrouter")
def salvar_openrouter(payload: OpenRouterIn, db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Chave do OpenRouter (provedor PRINCIPAL da cadeia de IA)."""
    if payload.openrouter_api_key is not None:
        gravar_config(db, {"openrouter_api_key": (payload.openrouter_api_key or "").strip()})
        registrar(db, "openrouter_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"ativado": bool((payload.openrouter_api_key or "").strip())})
    if payload.openrouter_modelos is not None:
        modelos = _normalizar_modelos(payload.openrouter_modelos)
        gravar_config(db, {"openrouter_modelos": modelos})
        registrar(db, "openrouter_modelos_alterado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"modelos": modelos})
    db.commit()
    return ver_groq(db, rh)


@router.post("/rh/config/openrouter/testar")
def testar_openrouter_rota(db: Session = Depends(get_db),
                           _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.ia_texto import chave_openrouter, testar_openrouter
    chave = chave_openrouter(db)
    if not chave:
        raise HTTPException(status_code=422, detail="chave_nao_configurada")
    try:
        texto = testar_openrouter(chave)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "texto_lido": (texto or "")[:120]}


@router.get("/rh/config/smtp")
def ver_smtp(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    cfg = smtp_config(db)
    return {
        "smtp_host": cfg["host"], "smtp_port": cfg["port"], "smtp_user": cfg["user"],
        "smtp_from": cfg["from_"], "senha_definida": bool(cfg["password"]),
    }


@router.put("/rh/config/smtp")
def salvar_smtp(payload: SmtpIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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


# ---------- Remetente de recrutamento (v2.68, § 16.1) ----------


class RecrutamentoIn(BaseModel):
    # Vazio é um valor VÁLIDO — é como se volta ao remetente padrão. Por isso
    # `str` com validação à mão, e não `EmailStr`, que recusaria a string vazia
    # e deixaria o RH sem como desfazer a configuração.
    email_recrutamento: str = ""


@router.get("/rh/config/recrutamento")
def ver_recrutamento(db: Session = Depends(get_db),
                     _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """O endereço de recrutamento e o estado da metade que NÃO é código.

    `depende_de_send_as` existe para a tela poder dizer a coisa certa: com o
    M365 conectado, o endereço só vale nos e-mails depois que o administrador
    liberar `Send As`. Sem ele, a tela prometeria algo que o tenant não cumpre
    — e o RH descobriria pelo endereço errado num convite já enviado.
    """
    from app.services.config_dinamica import CHAVE_EMAIL_RECRUTAMENTO, ler_config
    from app.services.m365 import config_m365

    bruto = (ler_config(db, (CHAVE_EMAIL_RECRUTAMENTO,))
             .get(CHAVE_EMAIL_RECRUTAMENTO) or "").strip()
    m365 = config_m365(db)
    return {
        "email_recrutamento": bruto,
        "padrao": smtp_config(db)["from_"],
        "depende_de_send_as": bool(m365.get("m365_refresh_token")),
        "conta_conectada": m365.get("m365_conta") or "",
    }


@router.put("/rh/config/recrutamento")
def salvar_recrutamento(payload: RecrutamentoIn, db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.config_dinamica import CHAVE_EMAIL_RECRUTAMENTO

    valor = (payload.email_recrutamento or "").strip()
    if valor and ("@" not in valor or valor.startswith("@") or valor.endswith("@")):
        raise HTTPException(status_code=422,
                            detail="Informe um endereço de e-mail válido "
                                   "(ou deixe em branco para usar o padrão).")
    gravar_config(db, {CHAVE_EMAIL_RECRUTAMENTO: valor})
    # Auditoria DEPOIS de validar a ação principal — nunca antes (a regra do
    # `registrar()`, que faz flush e engole exceção).
    registrar(db, "email_recrutamento_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"endereco": valor or "(padrão do sistema)"})
    db.commit()
    return ver_recrutamento(db, rh)


@router.post("/rh/config/smtp/testar")
def testar_smtp(db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
             _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
                rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
                   rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
def m365_desconectar(db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("config:escrever"))) -> None:
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
              _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
                 rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    valores = {"gmail_client_id": payload.client_id.strip()}
    if payload.client_secret:
        valores["gmail_client_secret"] = payload.client_secret.strip()
    gravar_config(db, valores)
    registrar(db, "gmail_config_alterada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_gmail(request, db, rh)


@router.get("/rh/config/gmail/url-login")
def gmail_url_login(request: Request, db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
def gmail_desconectar(db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("config:escrever"))) -> None:
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
def ver_webhook(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    url = webhook_email.url_webhook(db)
    return {"configurado": bool(url), "url_mascarada": _mascara_url(url)}


@router.put("/rh/config/webhook")
def salvar_webhook(payload: WebhookIn, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    url = (payload.webhook_url or "").strip()
    if url and not url.lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="url_precisa_ser_https")
    gravar_config(db, {"webhook_email_url": url})
    registrar(db, "webhook_email_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"ativado": bool(url)})
    db.commit()
    return ver_webhook(db, rh)


@router.post("/rh/config/webhook/testar")
def testar_webhook(db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
def ver_avisos(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
                  rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
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
def ver_teams(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    url = teams.url_teams(db)
    return {"configurado": bool(url), "url_mascarada": _mascara_url(url),
            "template": teams.template_teams(db)}


@router.put("/rh/config/teams")
def salvar_teams(payload: TeamsIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    url = payload.webhook_url
    if url and not url.strip().lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="url_precisa_ser_https")
    teams.salvar_config(db, url, payload.template)
    registrar(db, "teams_config_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"configurado": bool(teams.url_teams(db))})
    db.commit()
    return ver_teams(db, rh)


@router.post("/rh/config/teams/testar")
def testar_teams(db: Session = Depends(get_db), rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    if not teams.url_teams(db):
        raise HTTPException(status_code=422, detail="teams_nao_configurado")
    if not teams.enviar_mensagem(
            db, "✅ Teste do Portal de Admissão Green House — se você está vendo esta "
                "mensagem, o webhook do Teams está funcionando."):
        raise HTTPException(status_code=422, detail="falha_no_envio_ao_teams")
    registrar(db, "teams_teste_ok", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"ok": True}


# ---------- Textos dos e-mails (v2.06) ----------
# O RH vê TODOS os e-mails que o sistema manda, com as variáveis de cada um,
# edita o texto, confere no preview e tem histórico com restauração. O catálogo
# (quais e-mails existem, quais variáveis, quais são obrigatórias) vive em
# `services/email_templates.py` — aqui só entram as rotas.


class EmailTemplateIn(BaseModel):
    assunto: str
    corpo: str
    botao_texto: str | None = None


@router.get("/rh/config/emails")
def listar_emails(db: Session = Depends(get_db),
                  _rh: UsuarioRH = Depends(exige("config:escrever"))) -> list[dict]:
    from app.services.email_templates import listar
    return listar(db)


@router.get("/rh/config/emails/{chave}/versoes")
def versoes_email(chave: str, db: Session = Depends(get_db),
                  _rh: UsuarioRH = Depends(exige("config:escrever"))) -> list[dict]:
    from app.models.email_template import EmailTemplateVersao
    from app.services.email_templates import CATALOGO_POR_CHAVE
    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")
    versoes = db.scalars(
        select(EmailTemplateVersao)
        .where(EmailTemplateVersao.chave == chave)
        .order_by(EmailTemplateVersao.versao.desc())).all()
    return [{"versao": v.versao, "assunto": v.assunto, "corpo": v.corpo,
             "botao_texto": v.botao_texto, "autor": v.autor,
             "criado_em": v.criado_em} for v in versoes]


@router.post("/rh/config/emails/{chave}/preview")
def preview_email(chave: str, payload: EmailTemplateIn,
                  db: Session = Depends(get_db),
                  _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Renderiza o texto EM EDIÇÃO com dados de exemplo — sem salvar nada.

    Preview sobre o texto digitado (e não sobre o salvo) é o ponto: o RH vê o
    que vai sair ANTES de gravar.
    """
    from app.services.email_templates import (CATALOGO_POR_CHAVE,
                                              faltando_obrigatorias, modelo)
    from app.services.fichas import aplicar_variaveis
    from app.services.email import html_moderno
    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")
    m = modelo(chave)
    ctx = dict(m.exemplo)
    assunto = aplicar_variaveis(payload.assunto, ctx)
    corpo = aplicar_variaveis(payload.corpo, ctx)
    paragrafos = [p.strip().replace("\n", "<br>")
                  for p in corpo.split("\n\n") if p.strip()]
    url = ctx.get(m.botao_url_var) if m.botao_url_var else None
    html = html_moderno(m.rotulo, paragrafos,
                        botao_texto=payload.botao_texto if url else None,
                        botao_url=url or None)
    return {"assunto": assunto, "corpo": corpo, "html": html,
            "faltando": faltando_obrigatorias(chave, payload.assunto, payload.corpo)}


class DestinatariosIn(BaseModel):
    # aceita "a@x.com, b@y.com" ou lista — o RH digita separado por vírgula
    destinatarios: str | list[str] = ""
    ativo: bool = True


@router.put("/rh/config/emails/{chave}/destinatarios")
def salvar_destinatarios_email(chave: str, payload: DestinatariosIn,
                               db: Session = Depends(get_db),
                               rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Quem recebe um AVISO INTERNO, editado na própria tela do e-mail (v2.21).

    Grava na MESMA matriz de Configurações → Avisos internos — não é um segundo
    lugar de verdade, é a mesma fonte exposta onde o RH está editando o texto.
    Só vale para os avisos internos: os demais e-mails vão para a pessoa do
    processo (candidato, colaborador, assinante), não para uma lista.
    """
    from app.services.email_templates import CATALOGO_POR_CHAVE, modelo
    from app.services.notificacoes import email_valido, gravar_matriz, ler_matriz

    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")
    evento = modelo(chave).evento
    if not evento:
        raise HTTPException(status_code=422, detail={
            "erro": "email_sem_destinatario_configuravel",
            "motivo": "Este e-mail vai para a pessoa do processo (candidato, "
                      "colaborador ou assinante), não para uma lista fixa."})

    bruto = payload.destinatarios
    lista = bruto if isinstance(bruto, list) else bruto.replace(";", ",").split(",")
    emails = [e.strip() for e in lista if e and e.strip()]
    invalidos = [e for e in emails if not email_valido(e)]
    if invalidos:
        raise HTTPException(status_code=422, detail={
            "erro": "email_invalido", "invalidos": invalidos})

    matriz = ler_matriz(db)
    matriz[evento] = {"emails": emails, "ativo": payload.ativo}
    gravar_matriz(db, matriz)
    registrar(db, "aviso_destinatarios_alterados", ator="rh", ator_detalhe=rh.email,
              detalhe={"evento": evento, "quantidade": len(emails),
                       "ativo": payload.ativo})
    db.commit()
    return {"evento": evento, "destinatarios": emails, "ativo": payload.ativo}


@router.post("/rh/config/emails/{chave}/enviar-teste")
def enviar_teste_email(chave: str, payload: EmailTemplateIn,
                       db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Manda o e-mail EM EDIÇÃO para a própria caixa de quem está editando.

    O preview mostra como fica na tela; só o envio real mostra como o Gmail/
    Outlook renderiza de fato — que é onde a formatação costuma quebrar. Vai
    para `rh.email` e para mais ninguém: nunca para o candidato, e o RH não
    escolhe o destinatário (senão a tela de textos viraria disparador).

    Usa o texto DIGITADO, não o salvo — testar antes de gravar é o ponto.
    """
    from app.services.email_templates import CATALOGO_POR_CHAVE, modelo
    from app.services.fichas import aplicar_variaveis

    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")
    if not rh.email:
        raise HTTPException(status_code=422, detail="sem_email_no_seu_usuario")

    m = modelo(chave)
    ctx = dict(m.exemplo)
    assunto = aplicar_variaveis(payload.assunto, ctx)
    corpo = aplicar_variaveis(payload.corpo, ctx)
    paragrafos = [p.strip().replace("\n", "<br>")
                  for p in corpo.split("\n\n") if p.strip()]
    url = ctx.get(m.botao_url_var) if m.botao_url_var else None
    html = html_moderno(m.rotulo, paragrafos,
                        botao_texto=payload.botao_texto if url else None,
                        botao_url=url or None)
    # marca de teste no assunto: se algum dia vazar, fica evidente que é ensaio
    # (e o RH não confunde com um e-mail de verdade na própria caixa)
    try:
        enviado = enviar_email(
            rh.email, f"[TESTE] {assunto}",
            f"(Envio de teste do painel — dados de exemplo)\n\n{corpo}",
            html, levantar_erro=True)
    except Exception as exc:
        raise HTTPException(status_code=422,
                            detail=f"falha_no_envio: {exc}") from exc
    if not enviado:
        raise HTTPException(status_code=422, detail="smtp_nao_configurado")
    registrar(db, "email_template_teste_enviado", ator="rh", ator_detalhe=rh.email,
              detalhe={"chave": chave})
    db.commit()
    return {"enviado_para": rh.email}


@router.put("/rh/config/emails/{chave}")
def salvar_email(chave: str, payload: EmailTemplateIn,
                 db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Salva o texto e arquiva a versão ANTERIOR no histórico.

    Recusa (422) se faltar uma variável obrigatória: sem `{{codigo}}` num
    e-mail de acesso, a mensagem sai bonita e vazia — e ninguém mais entra no
    sistema. É o único jeito de o RH não se trancar para fora sem perceber.
    """
    from app.models.email_template import EmailTemplate, EmailTemplateVersao
    from app.services.email_templates import (CATALOGO_POR_CHAVE,
                                              faltando_obrigatorias,
                                              texto_vigente)
    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")
    assunto = (payload.assunto or "").strip()
    corpo = (payload.corpo or "").strip()
    if not assunto or not corpo:
        raise HTTPException(status_code=422, detail="assunto_e_corpo_obrigatorios")
    faltando = faltando_obrigatorias(chave, assunto, corpo)
    if faltando:
        raise HTTPException(status_code=422,
                            detail={"erro": "variaveis_obrigatorias", "faltando": faltando})

    # arquiva o que estava valendo antes de sobrescrever
    anterior_assunto, anterior_corpo, anterior_botao = texto_vigente(db, chave)
    ultima = db.scalar(
        select(func.max(EmailTemplateVersao.versao))
        .where(EmailTemplateVersao.chave == chave)) or 0
    db.add(EmailTemplateVersao(
        chave=chave, versao=ultima + 1, assunto=anterior_assunto,
        corpo=anterior_corpo, botao_texto=anterior_botao, autor=rh.email))

    t = db.get(EmailTemplate, chave)
    if t is None:
        t = EmailTemplate(chave=chave, assunto=assunto, corpo=corpo,
                          botao_texto=payload.botao_texto, atualizado_por=rh.email)
        db.add(t)
    else:
        t.assunto, t.corpo = assunto, corpo
        t.botao_texto = payload.botao_texto
        t.atualizado_por = rh.email
    registrar(db, "email_template_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"chave": chave, "versao_arquivada": ultima + 1})
    db.commit()
    return {"ok": True, "chave": chave}


@router.post("/rh/config/emails/{chave}/restaurar")
def restaurar_email(chave: str, versao: int | None = None,
                    db: Session = Depends(get_db),
                    rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Volta a uma versão do histórico; sem `versao`, volta ao texto de fábrica."""
    from app.models.email_template import EmailTemplate, EmailTemplateVersao
    from app.services.email_templates import CATALOGO_POR_CHAVE, modelo
    if chave not in CATALOGO_POR_CHAVE:
        raise HTTPException(status_code=404, detail="email_desconhecido")

    if versao is None:
        # de fábrica: some com a personalização e o padrão do catálogo volta a
        # valer sozinho (texto_vigente cai nele quando não há registro)
        t = db.get(EmailTemplate, chave)
        if t is not None:
            db.delete(t)
        registrar(db, "email_template_restaurado", ator="rh", ator_detalhe=rh.email,
                  detalhe={"chave": chave, "para": "padrao"})
        db.commit()
        m = modelo(chave)
        return {"ok": True, "assunto": m.assunto, "corpo": m.corpo,
                "botao_texto": m.botao_texto}

    v = db.scalar(select(EmailTemplateVersao).where(
        EmailTemplateVersao.chave == chave, EmailTemplateVersao.versao == versao))
    if v is None:
        raise HTTPException(status_code=404, detail="versao_nao_encontrada")
    return salvar_email(chave, EmailTemplateIn(
        assunto=v.assunto, corpo=v.corpo, botao_texto=v.botao_texto), db, rh)


# ---------- Limite de upload ----------


class TetoUploadIn(BaseModel):
    mb: int


@router.get("/rh/config/upload")
def ver_teto_upload(db: Session = Depends(get_db),
                    _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    from app.services.upload_seguro import (TETO_MB_MAX, TETO_MB_MIN,
                                            EXTENSOES_DOCUMENTO, teto_bytes)
    return {"mb": teto_bytes(db) // (1024 * 1024),
            "minimo": TETO_MB_MIN, "maximo": TETO_MB_MAX,
            "formatos": sorted(EXTENSOES_DOCUMENTO)}


@router.put("/rh/config/upload")
def salvar_teto_upload(payload: TetoUploadIn, db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Tamanho máximo de arquivo que o colaborador consegue enviar.

    Editável no painel (pedido do Bruno, 2026-08-02) porque limite chumbado no
    código exige deploy para ajustar — e quem descobre que o teto é pequeno
    demais é o RH, com o colaborador do outro lado da linha tentando mandar a
    foto de um celular novo.
    """
    from app.services.upload_seguro import (CHAVE_TETO_MB, TETO_MB_MAX,
                                            TETO_MB_MIN)
    if not (TETO_MB_MIN <= payload.mb <= TETO_MB_MAX):
        raise HTTPException(status_code=422, detail="fora_da_faixa")
    gravar_config(db, {CHAVE_TETO_MB: str(payload.mb)})
    registrar(db, "upload_teto_config", ator="rh", ator_detalhe=rh.email,
              detalhe={"mb": payload.mb})
    db.commit()
    return {"mb": payload.mb}


# ---------- Auditoria ----------


@router.get("/rh/auditoria")
def auditoria(db: Session = Depends(get_db), _rh: UsuarioRH = Depends(exige("dados:auditoria")),
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


# --------------------------------------------------------------------------
# EXIGÊNCIAS — o padrão da CASA (v2.80)
# --------------------------------------------------------------------------
# Pedido do Bruno: *"daí ter um padrão geral lá em configurações"*. Aqui se
# define o que vale para TODOS; a exceção por pessoa fica na ficha dela
# (`revisao.py`). A resolução em camadas mora em `services/exigencias.py`.

class ExigenciaPadraoIn(BaseModel):
    grupo: str                     # "documentos" | "campos"
    chave: str
    obrigatorio: bool | None = None   # None = volta ao padrão de FÁBRICA


@router.get("/rh/config/exigencias")
def ver_exigencias(db: Session = Depends(get_db),
                   _rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """O padrão da casa, com a origem de cada item (fábrica ou casa)."""
    from app.services.exigencias import dump_para_tela
    return dump_para_tela(db)          # sem candidato: só fábrica + casa


@router.put("/rh/config/exigencias")
def salvar_exigencia_padrao(payload: ExigenciaPadraoIn,
                            db: Session = Depends(get_db),
                            rh: UsuarioRH = Depends(exige("config:escrever"))) -> dict:
    """Muda o padrão para TODOS os candidatos daqui em diante.

    ⚠️ Vale para quem AINDA está preenchendo, não para quem já concluiu: as
    pendências são calculadas na hora de declarar. Tornar algo obrigatório não
    reabre ficha de ninguém — reabrir admissão encerrada é outro caminho, com
    outras guardas (v2.03/v2.43).

    `obrigatorio = None` remove a chave e devolve ao padrão de fábrica: sem isso
    o RH não teria como desfazer sem saber de cor qual era o valor original.
    """
    import json

    from app.api.revisao import _validar_exigencia
    from app.services.config_dinamica import ler_config
    from app.services.exigencias import CHAVE_CONFIG, ROTULOS

    # MESMA validação da rota por pessoa: duas cópias divergiriam na primeira
    # mudança, e é ela que guarda a regra de que `pessoais.email` e
    # `documentos.cpf` não se desmarcam — nem aqui, nem lá.
    grupo = (payload.grupo or "").strip()
    chave = (payload.chave or "").strip()
    _validar_exigencia(grupo, chave)

    bruto = ler_config(db, (CHAVE_CONFIG,)).get(CHAVE_CONFIG)
    try:
        atual = json.loads(bruto) if bruto else {}
        if not isinstance(atual, dict):
            atual = {}
    except (ValueError, TypeError):
        # Config ilegível não trava a gravação: começa do zero em vez de
        # devolver 500 e deixar o RH sem saída.
        atual = {}

    do_grupo = dict(atual.get(grupo) or {})
    if payload.obrigatorio is None:
        do_grupo.pop(chave, None)
    else:
        do_grupo[chave] = bool(payload.obrigatorio)
    atual[grupo] = do_grupo
    gravar_config(db, {CHAVE_CONFIG: json.dumps(
        {g: v for g, v in atual.items() if v}, ensure_ascii=False)})

    registrar(db, "exigencia_padrao_alterada", ator="rh", ator_detalhe=rh.email,
              detalhe={"grupo": grupo, "chave": chave,
                       "rotulo": ROTULOS.get(chave, chave),
                       "obrigatorio": payload.obrigatorio})
    db.commit()
    return {"ok": True, "grupo": grupo, "chave": chave,
            "obrigatorio": payload.obrigatorio}
