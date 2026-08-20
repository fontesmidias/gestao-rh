"""Link público único de levantamento do Reembolso-Creche (IN SEGES/MGI nº
147/2026). Todos os colaboradores recebem o MESMO link e se identificam por CPF.

Fluxo:
1. /creche/iniciar  {cpf}  -> localiza o colaborador na base, cria/recupera o
   benefício e envia um CÓDIGO de 6 dígitos ao e-mail (2FA). Se não houver
   e-mail na base, o colaborador informa um e-mail e o código vai para ele.
2. /creche/confirmar {cpf, email?, codigo} -> valida o código e devolve um TOKEN
   de sessão. Só APÓS confirmar é que os dados pré-preenchidos são revelados
   (LGPD: ninguém vê dado de terceiro digitando um CPF alheio).
3. Com o token: conferir dados, cadastrar crianças, subir certidão/guarda e
   enviar o levantamento para análise do RH.

A elegibilidade NÃO é revelada ao colaborador: o levantamento serve para a
análise interna de quem faz jus ao benefício, nos termos da IN 147/2026. Todos
preenchem; o RH decide.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from itsdangerous import BadSignature
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, get_settings, ip_do_cliente
from app.core.db import get_db
from app.models.beneficio import (AcessoCreche, BeneficioCreche, CriancaCreche,
                                  StatusBeneficio)
from app.models.candidato import Candidato, PostoServico
from app.models.ficha import DadosPessoais, Endereco
from app.services import kba, storage
from app.services.auditoria import registrar
from app.services.email_templates import enviar_modelo
from app.services.upload_seguro import (EXTENSOES_COM_WORD, extensao_de,
                                        ler_upload)
from app.services.validacao import cpf_valido

router = APIRouter(tags=["creche-publico"])

CODIGO_TTL_MIN = 15
SESSAO_TTL_H = 6
# Acesso direto (sem 2FA) mandado no e-mail de devolução: a pessoa lê o e-mail
# quando pode, então a janela é de dias — mas não é eterna, e cada devolução
# nova invalida a anterior.
ACESSO_DEVOLUCAO_TTL_D = 7
KBA_SALT = "creche-kba"


def _digitos(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


def _cpf_fmt(cpf: str) -> str:
    d = _digitos(cpf)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else cpf


def _hash(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()


def _colaborador_por_cpf(db: Session, cpf_digitos: str) -> Candidato | None:
    """Colaborador (situação preenchida) cujo CPF bate. Prioriza registros já
    colaboradores; ignora candidatos em admissão pura."""
    fmt = _cpf_fmt(cpf_digitos)
    cands = db.scalars(select(Candidato).where(Candidato.cpf.in_([fmt, cpf_digitos]))).all()
    # prioriza quem já é colaborador
    cands.sort(key=lambda c: (c.situacao is None, c.criado_em), reverse=False)
    for c in cands:
        if c.situacao:
            return c
    return cands[0] if cands else None


def _beneficio(db: Session, candidato: Candidato) -> BeneficioCreche:
    ben = db.scalar(select(BeneficioCreche)
                    .where(BeneficioCreche.candidato_id == candidato.id))
    if ben is None:
        ben = BeneficioCreche(candidato_id=candidato.id)
        db.add(ben)
        db.flush()
    return ben


def _sessao_valida(db: Session, token: str) -> tuple[AcessoCreche, BeneficioCreche] | None:
    ac = db.scalar(select(AcessoCreche).where(AcessoCreche.token_hash == _hash(token)))
    if ac is None or ac.confirmado_em is None:
        return None
    if ac.expira_em < datetime.now(timezone.utc):
        return None
    ben = db.get(BeneficioCreche, ac.beneficio_id)
    return (ac, ben) if ben else None


def _requer_sessao(token: str, db: Session) -> tuple[AcessoCreche, BeneficioCreche]:
    r = _sessao_valida(db, token)
    if r is None:
        raise HTTPException(status_code=401, detail="sessao_invalida")
    return r


# --------------------------------------------------------------------------
# 1) iniciar: CPF -> envia código 2FA
# --------------------------------------------------------------------------


def _gerar_e_enviar_codigo(db: Session, colaborador: Candidato,
                           ben: BeneficioCreche, email_destino: str,
                           base_url: str | None = None) -> None:
    """Cria um AcessoCreche pendente e envia o código 2FA ao e-mail. O e-mail é
    disparado APÓS o commit (SMTP fora não desfaz o registro).

    O token de RETOMADA (feedback 2026-07-28) vai no mesmo e-mail. Antes, o
    `token_hash` nascia com um placeholder e o token real só existia depois de
    acertar o código — então quem abria o link no app de e-mail, saía para ler
    o código e voltava, encontrava a tela zerada: o estado morava só na memória
    do navegador. Agora o link do e-mail identifica a pessoa desde o envio.

    O token IDENTIFICA, nunca AUTENTICA: enquanto `confirmado_em` é nulo ele só
    diz de quem é a tentativa (para o front repreencher o CPF e cobrar o
    código) e não abre dado nenhum — quem valida continua sendo o código.
    """
    codigo = f"{secrets.randbelow(10**6):06d}"
    token = secrets.token_urlsafe(32)
    ac = AcessoCreche(
        beneficio_id=ben.id,
        token_hash=_hash(token),
        codigo_hash=_hash(codigo),
        codigo_expira_em=datetime.now(timezone.utc) + timedelta(minutes=CODIGO_TTL_MIN),
        expira_em=datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H),
        # O LINK DO E-MAIL ENTRA DIRETO (decisão do Bruno, 2026-07-29): quem
        # recebeu o link na própria caixa já provou posse do e-mail, que é
        # exatamente o que o código de 6 dígitos prova. Pedir os dois é o mesmo
        # fator duas vezes — e foi o que travou o RH em campo. O código segue
        # no mesmo e-mail, para quem preferir digitar ou se o link quebrar no
        # app de e-mail. Contenção: o link vale o mesmo que o código (15 min,
        # `link_expira_em`), enquanto a SESSÃO que ele abre dura as 6h de
        # sempre.
        link_expira_em=datetime.now(timezone.utc) + timedelta(minutes=CODIGO_TTL_MIN),
    )
    db.add(ac)
    registrar(db, "creche_codigo_enviado", ator="colaborador",
              candidato_id=colaborador.id, detalhe={"cpf_final": _digitos(colaborador.cpf or "")[-4:]})
    db.commit()
    url = f"{base_url or get_settings().base_url}/creche?t={token}"
    _enviar_codigo(db, email_destino, colaborador.nome_completo, codigo, url)


def emitir_acesso_devolucao(db: Session, ben: BeneficioCreche) -> str:
    """Token de acesso DIRETO (sem 2FA) para o e-mail de devolução (v1.82).

    Afrouxamento consciente do gate, pedido pelo Bruno: quem foi devolvido já
    passou pelo 2FA alguma vez — o e-mail em `email_confirmado` é comprovado —
    e obrigá-lo a refazer o código só para corrigir um dado é atrito que faz a
    correção não voltar.

    O estrago fica contido porque o token:
      - vale ACESSO_DEVOLUCAO_TTL_D dias (não as 6h da sessão normal, porque a
        pessoa lê o e-mail quando pode; mas não é eterno);
      - é de USO ÚNICO no sentido de emissão — cada devolução emite um novo e
        INVALIDA os anteriores (`_invalidar_acessos`), então reenviar o e-mail
        mata o link antigo;
      - dá acesso a UM benefício e nada mais — o `ver_sessao` e as rotas de
        criança resolvem tudo a partir do `beneficio_id` do próprio acesso;
      - não reabre um pedido fechado: `add_crianca`/`enviar` recusam 409 fora
        do status `levantamento`, então um link vazado depois da aprovação não
        edita nada.

    O caller commita. O e-mail sai depois do commit.
    """
    _invalidar_acessos(db, ben)
    token = secrets.token_urlsafe(32)
    db.add(AcessoCreche(
        beneficio_id=ben.id,
        token_hash=_hash(token),
        # nasce já confirmado: a prova de identidade é o e-mail validado antes
        confirmado_em=datetime.now(timezone.utc),
        expira_em=datetime.now(timezone.utc) + timedelta(days=ACESSO_DEVOLUCAO_TTL_D),
    ))
    # é acesso SEM 2FA: fica na auditoria para se saber por que aquela sessão
    # existiu sem código (nunca o token, só o fato)
    registrar(db, "creche_acesso_direto_emitido", ator="rh",
              candidato_id=ben.candidato_id,
              detalhe={"motivo": "devolucao", "dias": ACESSO_DEVOLUCAO_TTL_D})
    return token


def _invalidar_acessos(db: Session, ben: BeneficioCreche) -> None:
    """Derruba as sessões vivas do benefício. Chamado ao emitir um acesso novo
    por e-mail: se o RH devolve duas vezes, só o último link funciona."""
    agora = datetime.now(timezone.utc)
    for ac in db.scalars(select(AcessoCreche).where(
            AcessoCreche.beneficio_id == ben.id,
            AcessoCreche.expira_em > agora)):
        ac.expira_em = agora


@router.get("/creche/retomar/{token}")
def retomar(token: str, db: Session = Depends(get_db)) -> dict:
    """Diz de QUEM é a tentativa por trás do `?t=` — sem autenticar ninguém e
    SEM CONSUMIR NADA.

    É o que conserta o ciclo do webview (feedback 2026-07-28): a pessoa abre o
    link no app de e-mail, sai para ler o código, volta pelo MESMO link e o
    servidor ainda sabe quem ela é. O que essa rota devolve é deliberadamente
    pobre — só o primeiro nome e os 4 últimos dígitos do CPF, o suficiente para
    o front repreencher o campo e mostrar "é você?".

    **GET NÃO TEM EFEITO COLATERAL** (incidente de campo 2026-07-30). Até a
    v2.27 esta rota CONSUMIA o link: confirmava o acesso e zerava
    `link_expira_em`. Só que quem abre o link primeiro, numa empresa com
    Microsoft 365, não é a pessoa — é o **Defender/Safe Links**, que pré-abre
    todo link do e-mail para escanear. O log de produção mostrou o padrão sem
    ambiguidade: a colaboradora PEDIA o código do IP do órgão e o
    `creche_entrou_pelo_link` chegava de IPs da Azure, segundos depois. O
    scanner ganhava a sessão, ela recebia "link expirado" e caía no código —
    que também falhava, porque cada novo pedido criava outro acesso. Sete
    e-mails, seis horas, nenhuma entrada.

    Por isso entrar virou POST (`/creche/entrar/{token}`): scanner nenhum faz
    POST. Aqui só se LÊ. ``pode_entrar`` sinaliza ao front que existe um link
    vivo a ser usado — quem decide usá-lo é o clique da pessoa.
    """
    agora = datetime.now(timezone.utc)
    ac = db.scalar(select(AcessoCreche).where(AcessoCreche.token_hash == _hash(token)))
    if ac is None or ac.expira_em < agora:
        raise HTTPException(status_code=404, detail="link_expirado")
    ben = db.get(BeneficioCreche, ac.beneficio_id)
    col = db.get(Candidato, ben.candidato_id) if ben else None
    if col is None:
        raise HTTPException(status_code=404, detail="link_expirado")

    # Sessão JÁ aberta (o acesso do RH na devolução nasce assim, e a pessoa que
    # já entrou e voltou também): entra direto, nada a consumir.
    ja_confirmado = ac.confirmado_em is not None
    # Link de código ainda válido: PODE virar sessão, mas só pelo POST.
    link_vivo = (not ja_confirmado
                 and ac.link_expira_em is not None
                 and ac.link_expira_em >= agora)

    nome = (col.nome_completo or "").split()
    return {
        "primeiro_nome": nome[0].title() if nome else "",
        "cpf_final": _digitos(col.cpf or "")[-4:],
        "pode_entrar": ja_confirmado,
        "pode_entrar_pelo_link": link_vivo,
        "aguardando_codigo": not ja_confirmado and not link_vivo,
    }


@router.post("/creche/entrar/{token}")
def entrar_pelo_link(token: str, db: Session = Depends(get_db)) -> dict:
    """Consuma o link do e-mail e abra a sessão — só por ATO DELIBERADO.

    Separado do `retomar` (GET) porque pré-fetch de antivírus corporativo
    queimava o link antes de a pessoa clicar (ver a docstring de `retomar`).
    Scanner de e-mail segue link; não envia POST.
    """
    agora = datetime.now(timezone.utc)
    ac = db.scalar(select(AcessoCreche).where(AcessoCreche.token_hash == _hash(token)))
    if ac is None or ac.expira_em < agora:
        raise HTTPException(status_code=404, detail="link_expirado")
    ben = db.get(BeneficioCreche, ac.beneficio_id)
    col = db.get(Candidato, ben.candidato_id) if ben else None
    if col is None:
        raise HTTPException(status_code=404, detail="link_expirado")

    if ac.confirmado_em is None:
        if ac.link_expira_em is None or ac.link_expira_em < agora:
            raise HTTPException(status_code=422, detail="link_expirado")
        ac.confirmado_em = agora
        ac.expira_em = agora + timedelta(hours=SESSAO_TTL_H)
        # uso único: o link não serve para uma segunda entrada
        ac.link_expira_em = agora
        registrar(db, "creche_entrou_pelo_link", ator="colaborador",
                  candidato_id=col.id)
        db.commit()
    return {"token": token}


class IniciarIn(BaseModel):
    cpf: str


@router.post("/creche/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """CPF -> se o colaborador existe E tem e-mail, envia o código 2FA. Caso
    contrário (sem e-mail OU CPF fora da base), responde EXATAMENTE o mesmo — sem
    revelar nada (anti-enumeração). Quem não recebeu o código usa o fluxo de
    verificação de identidade (KBA) para cadastrar/atualizar o e-mail."""
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    exigir(f"creche-ini:ip:{ip_do_cliente(request) or '?'}", maximo=10, janela_s=900)
    exigir(f"creche-ini:cpf:{cpf}", maximo=5, janela_s=900)

    colaborador = _colaborador_por_cpf(db, cpf)
    # Auditoria do RESULTADO (invisível ao usuário — a resposta abaixo é sempre a
    # mesma, anti-enumeração intacto). Serve ao relatório do RH para distinguir
    # "CPF realmente fora da base" de bug: quem tentou e não casou, ou casou mas
    # está sem e-mail (e por isso foi empurrado à KBA e pode ter falhado). O CPF
    # completo vai no detalhe de propósito — a auditoria é restrita ao RH.
    from app.services.auditoria import registrar
    if colaborador is None:
        registrar(db, "creche_iniciar_sem_match", ator="colaborador",
                  detalhe={"cpf": _cpf_fmt(cpf), "ip": ip_do_cliente(request)})
        db.commit()
    elif not colaborador.email:
        registrar(db, "creche_iniciar_sem_email", ator="colaborador",
                  candidato_id=colaborador.id,
                  detalhe={"cpf": _cpf_fmt(cpf), "nome": colaborador.nome_completo,
                           "situacao": colaborador.situacao})
        db.commit()
    else:
        ben = _beneficio(db, colaborador)
        db.commit()
        _gerar_e_enviar_codigo(db, colaborador, ben, colaborador.email,
                               base_url_publica(request))

    # Resposta SEMPRE idêntica — não distingue base-com-email, base-sem-email nem
    # fora-da-base. `pode_verificar_identidade` está sempre disponível.
    return {
        "pode_verificar_identidade": True,
        "mensagem": "Se este CPF constar em nossa base e houver e-mail cadastrado, "
                    "enviamos um código de confirmação. Verifique também a caixa de "
                    "spam. Não recebeu? Você pode confirmar sua identidade.",
    }


# --------------------------------------------------------------------------
# 1b) verificação de identidade (KBA) para quem não tem e-mail cadastrado:
#     CPF -> perguntas -> respostas -> cadastrar/atualizar e-mail -> código.
#     Reaproveita a KBA da entrada de admissão (app/services/kba.py).
# --------------------------------------------------------------------------


class KbaIniciarIn(BaseModel):
    cpf: str


@router.post("/creche/kba/iniciar")
def kba_iniciar(payload: KbaIniciarIn, request: Request,
                db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf)
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    ip = ip_do_cliente(request) or "-"
    exigir(f"creche-kba:ip:{ip}", maximo=10, janela_s=900)
    if kba.bloqueado(f"creche:cpf:{cpf}") or kba.bloqueado(f"creche:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    colaborador = _colaborador_por_cpf(db, cpf)
    # CPF fora da base / sem dados suficientes -> pool genérico (gabarito
    # impossível): resposta uniforme, nada revela.
    return kba.montar_desafio(db, colaborador, KBA_SALT, extra_payload={"cpf": cpf})


class KbaResponderIn(BaseModel):
    desafio: str
    respostas: dict[str, str]


@router.post("/creche/kba/responder")
def kba_responder(payload: KbaResponderIn, request: Request,
                  db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.desafio, max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="desafio_expirado")
    cpf = dados["cpf"]
    if kba.bloqueado(f"creche:cpf:{cpf}") or kba.bloqueado(f"creche:ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    if not kba.conferir_respostas(dados["gabarito"], payload.respostas):
        kba.registrar_falha(f"creche:cpf:{cpf}", f"creche:ip:{ip}")
        registrar(db, "creche_kba_falhou", ator="colaborador",
                  detalhe={"cpf_final": cpf[-4:], "ip": ip})
        db.commit()
        raise HTTPException(status_code=422, detail="nao_confirmado")
    colaborador = _colaborador_por_cpf(db, cpf)
    registrar(db, "creche_kba_ok", ator="colaborador",
              candidato_id=colaborador.id if colaborador else None, detalhe={"ip": ip})
    db.commit()
    # token curto que autoriza cadastrar/atualizar o e-mail
    autorizacao = kba.serializer(KBA_SALT).dumps({"cpf": cpf, "kba_ok": True})
    return {"autorizacao": autorizacao}


class KbaDefinirEmailIn(BaseModel):
    autorizacao: str
    email: str


@router.post("/creche/kba/definir-email")
def kba_definir_email(payload: KbaDefinirEmailIn, request: Request,
                      db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = kba.serializer(KBA_SALT).loads(payload.autorizacao, max_age=kba.DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="autorizacao_expirada")
    if not dados.get("kba_ok"):
        raise HTTPException(status_code=422, detail="autorizacao_invalida")
    email = (payload.email or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="email_invalido")
    colaborador = _colaborador_por_cpf(db, dados["cpf"])
    if colaborador is None:
        # KBA só passa para CPF real; guarda de segurança adicional.
        raise HTTPException(status_code=422, detail="nao_confirmado")
    ben = _beneficio(db, colaborador)
    # atualiza o e-mail do cadastro (identidade já confirmada pela KBA)
    colaborador.email = email
    ben.email_confirmado = email
    registrar(db, "creche_email_atualizado_kba", ator="colaborador",
              candidato_id=colaborador.id, detalhe={"ip": ip})
    db.commit()
    _gerar_e_enviar_codigo(db, colaborador, ben, email, base_url_publica(request))
    return {"ok": True}


def _enviar_codigo(db: Session, email: str, nome: str, codigo: str,
                   url: str | None = None) -> None:
    """Código 2FA + link de RETOMADA no mesmo e-mail.

    O link é o que permite sair do e-mail para ler o código e VOLTAR sem perder
    a tentativa (o app de e-mail abre o site numa janela própria, que morre ao
    trocar de tela). Ele não substitui o código — só devolve a pessoa ao ponto
    onde estava, com o CPF já reconhecido.
    """
    enviar_modelo(db, "creche_codigo", email, {
        "primeiro_nome": (nome or "").split()[0].title() if nome else "",
        "codigo": codigo, "ttl": CODIGO_TTL_MIN, "link": url,
    })


class ConfirmarIn(BaseModel):
    cpf: str | None = None
    codigo: str
    email: str | None = None
    # token do link do e-mail: quem voltou por ele não redigita o CPF
    retomada: str | None = None


@router.post("/creche/confirmar")
def confirmar(payload: ConfirmarIn, db: Session = Depends(get_db)) -> dict:
    from app.services.limite import exigir
    cpf = _digitos(payload.cpf or "")
    colaborador = None
    if payload.retomada:
        # O token identifica a tentativa; o CÓDIGO continua sendo o que
        # autentica (ver `retomar`). Serve só para dispensar o CPF digitado.
        ac_ret = db.scalar(select(AcessoCreche)
                           .where(AcessoCreche.token_hash == _hash(payload.retomada)))
        if ac_ret is not None and ac_ret.expira_em >= datetime.now(timezone.utc):
            ben_ret = db.get(BeneficioCreche, ac_ret.beneficio_id)
            colaborador = db.get(Candidato, ben_ret.candidato_id) if ben_ret else None
            if colaborador is not None:
                cpf = _digitos(colaborador.cpf or "") or cpf
    # código de 6 dígitos: 10 tentativas por CPF na janela e acabou
    exigir(f"creche-2fa:cpf:{cpf}", maximo=10, janela_s=900)
    if colaborador is None:
        colaborador = _colaborador_por_cpf(db, cpf)
    if colaborador is None:
        raise HTTPException(status_code=422, detail="codigo_invalido")
    ben = _beneficio(db, colaborador)
    # O acesso mais recente que ainda tem código válido — CONFIRMADO OU NÃO.
    # Antes exigia `confirmado_em IS NULL`, e quem entrava pelo link (v2.17) e
    # digitava o código em seguida levava "código inválido" com o código certo
    # na mão: o link já tinha confirmado aquele acesso. O código continua
    # sendo conferido; o que mudou é não descartar o registro por já ter sido
    # aberto pelo link do MESMO e-mail.
    #
    # QUALQUER código ainda dentro da validade vale (2026-07-30). Antes só o
    # acesso MAIS RECENTE era conferido: quem pedia um segundo código — porque
    # o primeiro "não funcionou" — invalidava calado o e-mail que estava aberto
    # na tela, e digitar o código de cima levava "código inválido" com o código
    # certo na mão. É a mesma garantia que a assinatura e o teste já davam
    # (lá o código é sobrescrito no MESMO registro, então o último sempre vale);
    # aqui cada pedido cria um AcessoCreche novo, então a equivalência exige
    # conferir todos os vivos. A validade de 15 min e a cota de 10 tentativas
    # por CPF continuam sendo o que limita.
    agora = datetime.now(timezone.utc)
    vivos = db.scalars(
        select(AcessoCreche)
        .where(AcessoCreche.beneficio_id == ben.id,
               AcessoCreche.codigo_hash.isnot(None),
               AcessoCreche.codigo_expira_em >= agora)
        .order_by(AcessoCreche.criado_em.desc())
    ).all()
    informado = _hash(payload.codigo.strip())
    ac = next((a for a in vivos if a.codigo_hash == informado), None)
    if ac is None:
        # Tentativa fracassada é REGISTRO, não silêncio: 422 repetido no mesmo
        # CPF é o sinal mais forte de gente travada, e até 2026-07-30 não ia
        # para lugar nenhum — a colaboradora tentou seis horas e o relatório
        # "Não conseguiram acessar" não a via.
        registrar(db, "creche_codigo_recusado", ator="colaborador",
                  candidato_id=colaborador.id,
                  detalhe={"cpf": _cpf_fmt(cpf), "nome": colaborador.nome_completo,
                           "codigos_vivos": len(vivos)})
        db.commit()
        raise HTTPException(status_code=422, detail="codigo_invalido")

    # emite token de sessão real
    token = secrets.token_urlsafe(32)
    ac.token_hash = _hash(token)
    ac.confirmado_em = datetime.now(timezone.utc)
    ac.expira_em = datetime.now(timezone.utc) + timedelta(hours=SESSAO_TTL_H)
    # o e-mail já foi cadastrado no /iniciar (com e-mail) ou na KBA; o campo do
    # payload permanece só como fallback de compatibilidade.
    ben.email_confirmado = colaborador.email or (payload.email or "").strip() or ben.email_confirmado
    ben.email_confirmado_em = datetime.now(timezone.utc)
    registrar(db, "creche_2fa_confirmado", ator="colaborador",
              candidato_id=colaborador.id)
    db.commit()
    return {"token": token}


# --------------------------------------------------------------------------
# 3) sessão: dados pré-preenchidos, crianças, upload, envio
# --------------------------------------------------------------------------


def _dump_crianca(c: CriancaCreche) -> dict:
    return {"id": c.id, "nome": c.nome, "data_nascimento": c.data_nascimento,
            "parentesco": c.parentesco, "tipo_comprovante": c.tipo_comprovante,
            "tem_certidao": bool(c.certidao_key), "tem_guarda": bool(c.guarda_key),
            # Resultado POR CRIANÇA, com o motivo (v2.55, decisão do Bruno).
            # Segue a regra da casa desde o portal `/meu`: o motivo da recusa é
            # visível ao colaborador. Sem isso, quem tem dois filhos e vê o
            # benefício aprovado não descobre que um deles ficou de fora — e
            # liga para o RH perguntar, ou pior, não liga e descobre na folha.
            # `decidido_por`/`decidido_em` NÃO vão: quem decidiu é assunto
            # interno, e nomear o analista transformaria a decisão em disputa
            # pessoal (mesmo raciocínio dos fatos observados no desempenho).
            "decisao": c.decisao,
            "motivo_decisao": c.motivo_decisao}


@router.get("/creche/sessao/{token}")
def ver_sessao(token: str, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    col = db.get(Candidato, ben.candidato_id)
    p = db.get(DadosPessoais, col.id)
    e = db.get(Endereco, col.id)
    # dados pré-preenchidos da base — o colaborador confere e confirma/atualiza
    return {
        "status": ben.status,
        "nome_completo": col.nome_completo,
        "cpf": col.cpf,
        "email": ben.email_confirmado or col.email,
        "telefone": ben.telefone or col.celular_whatsapp,
        "cargo": col.cargo_funcao,
        "posto": (db.get(PostoServico, col.posto_servico_id).nome
                  if col.posto_servico_id else None),
        "endereco": (e.logradouro_numero_complemento if e else None),
        "cidade": (e.cidade if e else None),
        "dados_conferidos": ben.dados_conferidos_em is not None,
        "criancas": [_dump_crianca(c) for c in ben.criancas],
        "editavel": ben.status in (StatusBeneficio.levantamento,),
        # Se o RH devolveu para correção, o colaborador vê o motivo ao reabrir
        # (feedback 2026-07-21) — só faz sentido enquanto estiver editável.
        "motivo_devolucao": (ben.motivo_devolucao
                             if ben.status == StatusBeneficio.levantamento else None),
        # o motivo do indeferimento também é da pessoa (ela passou por 2FA) —
        # mostrá-lo evita a enxurrada de "por que fui indeferido?" (2026-07-22).
        "motivo_indeferimento": (ben.motivo_indeferimento
                                 if ben.status == StatusBeneficio.indeferido else None),
    }


class ConferirDadosIn(BaseModel):
    email: str | None = None
    telefone: str | None = None


@router.put("/creche/sessao/{token}/dados")
def conferir_dados(token: str, payload: ConferirDadosIn, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    if payload.email is not None:
        ben.email_confirmado = payload.email.strip() or ben.email_confirmado
    if payload.telefone is not None:
        ben.telefone = payload.telefone.strip() or None
    ben.dados_conferidos_em = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


class CriancaIn(BaseModel):
    # ISO (aaaa-mm-dd) ou BR (dd/mm/aaaa) — o `InputData.jsx` devolve ISO por
    # padrão e é assim que a maioria dos registros foi gravada. Ver
    # `creche.partes_da_data`, que lê os dois.
    nome: str
    data_nascimento: str
    parentesco: str       # filho | enteado | guarda
    tipo_comprovante: str | None = None  # declaracao | nota_fiscal


_ROTULO_DOC_CRIANCA = {"certidao": "certidão de nascimento",
                       "guarda": "guarda judicial"}

# Quem cuida da criança define QUAL documento comprova a despesa todo mês
# (art. 11, II da IN SEGES/MGI 147/2026; e-mail do Jurídico de 18/08/2026):
# creche/pré-escola é PJ e emite NOTA FISCAL; cuidador pessoa física assina a
# DECLARAÇÃO DE QUITAÇÃO. O sistema não tem como conferir se o arquivo enviado é
# mesmo uma nota fiscal — o que ele garante é que o tipo esteja DECLARADO, para
# saber o que cobrar e para a tela dizer à pessoa o que anexar.
TIPOS_COMPROVANTE = ("declaracao", "nota_fiscal")


def _guardar_doc_crianca(beneficio_id, crianca_id: str, tipo: str,
                         arquivo, conteudo: bytes) -> str:
    """Grava o documento da criança como PDF TIMBRADO, e devolve a key.

    Pedido do Bruno (2026-08-02): *"para o RH e/ou quando gerar o dossiê, já vir
    no padrão conforme documentos anteriores, no timbrado da empresa"*.

    Até aqui o creche gravava o arquivo CRU: a certidão fotografada ficava como
    um `.jpg` no MinIO, enquanto no wizard da admissão a mesma foto vira uma
    A4 timbrada. Passa pela MESMA `normalizar_para_pdf` do wizard — que, além do
    timbre, converte HEIC (foto de iPhone), recusa imagem borrada ou pequena
    demais e valida que o PDF abre.

    **Falha de normalização NÃO perde o documento**: se a conversão não der
    conta (formato exótico, PDF protegido), grava o original. Recusar aqui
    deixaria a pessoa sem conseguir enviar a certidão do filho — e o benefício
    trava por causa da qualidade de uma foto, não do direito dela. O RH ainda
    vê o arquivo; só não sai timbrado.
    """
    from app.services.normalizacao import normalizar_para_pdf

    nome = arquivo.filename or f"{tipo}.bin"
    rotulo = _ROTULO_DOC_CRIANCA.get(tipo, tipo)
    try:
        pdf, _paginas = normalizar_para_pdf(nome, conteudo, rotulo=rotulo)
    except Exception:
        # Qualquer falha (formato recusado, imagem borrada, PDF protegido) cai
        # no original — ver o porquê no docstring. `Exception` abrange tanto o
        # `ArquivoInvalido` quanto um erro inesperado da conversão: o desfecho
        # desejado é o mesmo nos dois casos.
        ext = extensao_de(arquivo) or "bin"
        key = f"creche/{beneficio_id}/{crianca_id}/{tipo}.{ext}"
        storage.salvar(key, conteudo,
                       arquivo.content_type or "application/octet-stream")
        return key
    key = f"creche/{beneficio_id}/{crianca_id}/{tipo}.pdf"
    storage.salvar(key, pdf, "application/pdf")
    return key


def _conferir_data_da_crianca(valor: str) -> None:
    """Barra data que não é de criança ANTES de gravar.

    Existe por causa do caso de 2026-08-02: o nascimento do próprio
    colaborador (12/10/1998) entrou no campo do filho, e o painel do RH passou
    a mostrar "27a 9m · ❌ passou de 5a11m" para uma criança nascida em 2022 —
    marcando ainda o benefício como risco de glosa. O campo aceitava qualquer
    data que EXISTISSE; ninguém perguntava se ela era plausível.

    Duas recusas, as duas com 422 e motivo próprio para a tela explicar:
    data no FUTURO (não existe criança que ainda vai nascer) e idade de adulto.
    Consertar na origem é mais barato que o RH descobrir na hora de deferir —
    e evita o registro sujo que ninguém pode migrar em lote depois.
    """
    from app.api.creche import IDADE_IMPLAUSIVEL_ANOS, _idade_anos_meses, partes_da_data

    if partes_da_data(valor) is None:
        raise HTTPException(status_code=422, detail="data_invalida")
    idade = _idade_anos_meses(valor)
    if idade is None:                       # nascimento no futuro
        raise HTTPException(status_code=422, detail="data_no_futuro")
    if idade[0] >= IDADE_IMPLAUSIVEL_ANOS:
        raise HTTPException(status_code=422, detail="data_de_adulto")


@router.post("/creche/sessao/{token}/criancas", status_code=201)
def add_crianca(token: str, payload: CriancaIn, db: Session = Depends(get_db)) -> dict:
    _, ben = _requer_sessao(token, db)
    if ben.status != StatusBeneficio.levantamento:
        raise HTTPException(status_code=409, detail="levantamento_encerrado")
    if payload.parentesco not in ("filho", "enteado", "guarda"):
        raise HTTPException(status_code=422, detail="parentesco_invalido")
    if payload.tipo_comprovante not in TIPOS_COMPROVANTE:
        # Aceitar qualquer string deixaria entrar um valor que nenhuma tela
        # entende, e o comprovante do mês ficaria sem saber o que exigir.
        raise HTTPException(status_code=422, detail={
            "erro": "tipo_comprovante_invalido", "aceitos": list(TIPOS_COMPROVANTE)})
    _conferir_data_da_crianca(payload.data_nascimento.strip())
    c = CriancaCreche(
        beneficio_id=ben.id, nome=payload.nome.strip(),
        data_nascimento=payload.data_nascimento.strip(),
        parentesco=payload.parentesco,
        tipo_comprovante=payload.tipo_comprovante)
    db.add(c)
    db.commit()
    return _dump_crianca(c)


class TipoComprovanteIn(BaseModel):
    tipo_comprovante: str


@router.put("/creche/sessao/{token}/criancas/{crianca_id}/tipo-comprovante")
def definir_tipo_comprovante(token: str, crianca_id: str, payload: TipoComprovanteIn,
                             db: Session = Depends(get_db)) -> dict:
    """Quem cuida da criança: creche/pré-escola (PJ) ou cuidador pessoa física.

    Existe porque o tipo só podia ser escolhido AO CRIAR a criança — e quem
    começou pelo wizard da admissão pode tê-la cadastrado sem saber ainda onde
    ela ficaria. Sem esta rota, a pessoa era cobrada no envio (`tipo_comprovante
    _faltando`) e não tinha onde responder: recusa sem saída (v2.87).
    """
    _, ben = _requer_sessao(token, db)
    if ben.status != StatusBeneficio.levantamento:
        raise HTTPException(status_code=409, detail="envio_ja_concluido")
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if payload.tipo_comprovante not in TIPOS_COMPROVANTE:
        raise HTTPException(status_code=422, detail={
            "erro": "tipo_comprovante_invalido", "aceitos": list(TIPOS_COMPROVANTE)})
    c.tipo_comprovante = payload.tipo_comprovante
    db.commit()
    return _dump_crianca(c)


@router.delete("/creche/sessao/{token}/criancas/{crianca_id}", status_code=204)
def del_crianca(token: str, crianca_id: str, db: Session = Depends(get_db)) -> None:
    _, ben = _requer_sessao(token, db)
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    db.delete(c)
    db.commit()


@router.post("/creche/sessao/{token}/criancas/{crianca_id}/documento")
async def subir_documento(token: str, crianca_id: str, tipo: str, arquivo: UploadFile,
                          db: Session = Depends(get_db)) -> dict:
    """Sobe certidão de nascimento (tipo=certidao) ou guarda judicial
    (tipo=guarda) da criança."""
    _, ben = _requer_sessao(token, db)
    c = db.get(CriancaCreche, crianca_id)
    if c is None or c.beneficio_id != ben.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    # Teto de tamanho, extensão da lista e — principalmente — `close()` do
    # spool. Esta rota é PÚBLICA e gravava qualquer coisa, de qualquer tamanho,
    # deixando o arquivo temporário no container: o que sobrava ali era
    # certidão de nascimento de criança (v2.56).
    # `EXTENSOES_COM_WORD`: a câmera guiada oferece o seletor de arquivo com
    # `.doc/.docx` (v2.61), e recusar aqui devolveria "formato não suportado"
    # para um envio que a própria tela ofereceu.
    conteudo = await ler_upload(db, arquivo, EXTENSOES_COM_WORD)
    key = _guardar_doc_crianca(ben.id, crianca_id, tipo, arquivo, conteudo)
    if tipo == "certidao":
        c.certidao_key = key
    else:
        c.guarda_key = key
    db.commit()
    return _dump_crianca(c)


@router.post("/creche/sessao/{token}/enviar")
def enviar(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Fecha o levantamento e envia para análise do RH."""
    _, ben = _requer_sessao(token, db)
    if not ben.criancas:
        raise HTTPException(status_code=422, detail="sem_criancas")
    faltando = [c.nome for c in ben.criancas if not c.certidao_key]
    if faltando:
        raise HTTPException(status_code=422,
                            detail={"erro": "certidao_faltando", "criancas": faltando})
    # Quem entra por GUARDA JUDICIAL precisa do termo, além da certidão (pedido
    # do Bruno, 18/08/2026: *"se for questão de tutela ou guarda, precisa da
    # documentação, bem como a certidão de nascimento"*). Até aqui só a certidão
    # era cobrada: o levantamento fechava sem o documento que PROVA o vínculo, e
    # o RH descobria na análise — devolvendo o levantamento inteiro e esperando.
    # Filho e enteado não entram: para eles a certidão já é a prova.
    sem_guarda = [c.nome for c in ben.criancas
                  if c.parentesco == "guarda" and not c.guarda_key]
    if sem_guarda:
        raise HTTPException(status_code=422,
                            detail={"erro": "guarda_faltando", "criancas": sem_guarda})
    # QUEM CUIDA define o documento que virá todo mês (art. 11, II da IN 147):
    # creche/pré-escola (PJ) emite nota fiscal; cuidador pessoa física assina a
    # declaração de quitação. Sem esta informação o sistema não sabe o que
    # cobrar, e a pessoa descobre a exigência só no primeiro mês — quando o
    # prazo já está correndo. Quem começou pela admissão pode ter deixado em
    # branco (lá o arranjo ainda não está definido); aqui é o momento de
    # responder, porque é daqui que o benefício segue para análise.
    sem_tipo = [c.nome for c in ben.criancas if not c.tipo_comprovante]
    if sem_tipo:
        raise HTTPException(status_code=422,
                            detail={"erro": "tipo_comprovante_faltando",
                                    "criancas": sem_tipo})
    ben.status = StatusBeneficio.em_analise
    ben.enviado_em = datetime.now(timezone.utc)
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_levantamento_enviado", ator="colaborador",
              candidato_id=col.id, detalhe={"criancas": len(ben.criancas)})
    db.commit()
    # avisa o RH que entrou pedido na fila (v1.82) — destinatários configuráveis
    from app.services.notificacoes import avisar_modelo
    avisar_modelo(
        db, "creche_levantamento_enviado", "aviso_creche_levantamento",
        {"nome": col.nome_completo, "criancas": len(ben.criancas)})
    return {"status": ben.status}


@router.post("/creche/sessao/{token}/sem-direito")
def declarar_sem_direito(token: str, request: Request,
                         db: Session = Depends(get_db)) -> dict:
    """O colaborador DECLARA que não tem criança elegível ao benefício.

    Deixou de ser uma saída discreta e passou a ser uma das DUAS respostas
    possíveis, lado a lado, no topo do link (v2.34 — pedido do Bruno em
    2026-07-30):

        *"eu quero fazer um movimento que a pessoa manifeste que de fato tem ou
        não tem crianças, e não simplesmente entrar no link e, como não tem, não
        fazer nada e sair. E hoje a pessoa pode não ter filhos, mas amanhã pode
        ter — então é importante deixar tudo bem registrado."*

    A diferença é jurídica, não cosmética: sem manifestação, "não respondeu" e
    "não tem direito" são a MESMA linha em branco na planilha, e daqui a dois
    anos ninguém consegue demonstrar que o elegível foi consultado. Por isso o
    registro guarda **quem, quando e por qual caminho** — e a auditoria fica
    com o IP, que é o que sustenta a declaração se ela for contestada.

    Reversível de propósito: quem passa a ter filho usa o mesmo link (o RH
    reabre em `/reabrir`). Declarar hoje não fecha a porta amanhã.
    """
    _, ben = _requer_sessao(token, db)
    if ben.status != StatusBeneficio.levantamento:
        raise HTTPException(status_code=409, detail="levantamento_encerrado")
    # Guarda de coerência: quem já cadastrou criança não pode declarar que não
    # tem nenhuma sem antes removê-las — senão o registro contradiz o dado ao
    # lado dele, e é o registro que o RH vai usar como prova.
    if ben.criancas:
        raise HTTPException(status_code=409, detail="ha_criancas_cadastradas")
    ben.status = StatusBeneficio.sem_direito_declarado
    ben.sem_direito_em = datetime.now(timezone.utc)
    ben.sem_direito_por = "colaborador"
    col = db.get(Candidato, ben.candidato_id)
    registrar(db, "creche_sem_direito", ator="colaborador",
              candidato_id=ben.candidato_id,
              detalhe={"por": "colaborador", "nome": col.nome_completo if col else None,
                       "ip": ip_do_cliente(request)})
    db.commit()
    return {"status": ben.status}


# --------------------------------------------------------------------------
# Assinatura do requerimento pela plataforma (após aprovação do RH). O
# colaborador assina na PRÓPRIA sessão de creche (já autenticada por 2FA);
# depois o RH contra-assina pela fila /rh/minhas-assinaturas.
# --------------------------------------------------------------------------


def _etapa_colaborador(db: Session, ben: BeneficioCreche):
    """A etapa (ordem 1) do colaborador no roteiro do requerimento, se houver."""
    from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                                   SolicitacaoAssinatura)
    from app.services.roteiro_assinatura import tem_roteiro
    sol = tem_roteiro(db, ben.candidato_id)
    if sol is None or sol.origem != "creche_requerimento":
        return None, None
    etapa = db.scalar(select(EtapaAssinatura)
                      .where(EtapaAssinatura.solicitacao_id == sol.id,
                             EtapaAssinatura.ordem == 1))
    return sol, etapa


@router.get("/creche/sessao/{token}/requerimento")
def status_requerimento(token: str, db: Session = Depends(get_db)) -> dict:
    """Diz à sessão se há requerimento a assinar (benefício aprovado), se o
    colaborador já assinou e se o documento foi concluído."""
    from app.models.solicitacao_assinatura import StatusSolicitacao
    _, ben = _requer_sessao(token, db)
    sol, etapa = _etapa_colaborador(db, ben)
    if sol is None or etapa is None:
        return {"disponivel": False}
    return {
        "disponivel": True,
        "assinado": etapa.assinado_em is not None,
        "na_vez": etapa.ordem == sol.etapa_atual_ordem
                  and sol.status == StatusSolicitacao.aguardando,
        "concluido": sol.status == StatusSolicitacao.concluida,
    }


@router.post("/creche/sessao/{token}/assinar-requerimento")
def assinar_requerimento(token: str, request: Request,
                         db: Session = Depends(get_db)) -> dict:
    """Registra a assinatura do colaborador no requerimento — a sessão de creche
    já é o 2º fator (2FA por código no e-mail). Idempotente e serializado pelo
    avancar_solicitacao (correções C3/C7 do multi-signatário)."""
    import hashlib

    from app.models.solicitacao_assinatura import StatusSolicitacao
    from app.services.creche_pdf import gerar_requerimento_creche
    from app.services.roteiro_assinatura import avancar_solicitacao
    _, ben = _requer_sessao(token, db)
    sol, etapa = _etapa_colaborador(db, ben)
    if sol is None or etapa is None:
        raise HTTPException(status_code=404, detail="requerimento_indisponivel")
    if etapa.assinado_em is not None:
        raise HTTPException(status_code=409, detail="ja_assinado")
    if sol.status != StatusSolicitacao.aguardando or etapa.ordem != sol.etapa_atual_ordem:
        raise HTTPException(status_code=409, detail="fora_da_vez")
    col = db.get(Candidato, ben.candidato_id)
    # hash do documento SEM blocos (evidência) — mesmo critério do fluxo do wizard
    pdf_sem_bloco = gerar_requerimento_creche(db, ben)
    agora = datetime.now(timezone.utc)
    etapa.assinado_em = agora
    etapa.assinante_nome = col.nome_completo
    etapa.assinante_cpf = col.cpf
    etapa.ip = ip_do_cliente(request)
    etapa.user_agent = request.headers.get("user-agent", "")[:400]
    etapa.prova_metodo = "otp_creche"
    etapa.hash_sha256 = hashlib.sha256(pdf_sem_bloco).hexdigest()
    registrar(db, "creche_requerimento_assinado", ator="colaborador",
              candidato_id=col.id, detalhe={"solicitacao": str(sol.id)})
    db.commit()
    resultado = avancar_solicitacao(db, sol.id)
    db.commit()
    return {"assinado": True, "concluido": resultado["concluida"]}


# ==========================================================================
# Coleta de creche DENTRO da admissão: o candidato já autenticado pelo link
# mágico informa as crianças, se o posto dele dá direito. Sem 2FA (a admissão
# já autentica). Reaproveita BeneficioCreche/CriancaCreche.
# ==========================================================================


@router.get("/c/{token}/creche")
def creche_admissao_status(token: str, db: Session = Depends(get_db)) -> dict:
    """Diz ao wizard de admissão se o posto do candidato dá direito ao
    reembolso-creche e devolve as crianças já informadas. Se o posto não é
    elegível, o bloco nem aparece."""
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    posto = db.get(PostoServico, cand.posto_servico_id) if cand.posto_servico_id else None
    elegivel = bool(posto and posto.da_direito_creche)
    ben = db.scalar(select(BeneficioCreche)
                    .where(BeneficioCreche.candidato_id == cand.id)) if elegivel else None
    return {
        "posto_da_direito": elegivel,
        "posto": posto.nome if posto else None,
        "criancas": [_dump_crianca(c) for c in ben.criancas] if ben else [],
    }


@router.post("/c/{token}/creche/criancas", status_code=201)
def creche_admissao_add(token: str, payload: CriancaIn, db: Session = Depends(get_db)) -> dict:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    posto = db.get(PostoServico, cand.posto_servico_id) if cand.posto_servico_id else None
    if not (posto and posto.da_direito_creche):
        raise HTTPException(status_code=409, detail="posto_nao_elegivel")
    if payload.parentesco not in ("filho", "enteado", "guarda"):
        raise HTTPException(status_code=422, detail="parentesco_invalido")
    # Mesma trava do link público: a criança entra pelos DOIS caminhos, e
    # validar só um deixaria a porta que ninguém olha aberta.
    _conferir_data_da_crianca(payload.data_nascimento.strip())
    ben = db.scalar(select(BeneficioCreche).where(BeneficioCreche.candidato_id == cand.id))
    if ben is None:
        ben = BeneficioCreche(candidato_id=cand.id, email_confirmado=cand.email)
        db.add(ben)
        db.flush()
    # ⚠️ Aqui o tipo pode legitimamente ainda NÃO ser conhecido: na admissão a
    # pessoa muitas vezes não sabe onde a criança vai ficar. Por isso `None` é
    # aceito nesta porta (e cobrado depois, no link do creche) — mas valor
    # INVENTADO não passa: o comentário acima já registra que validar só uma das
    # portas deixa aberta a que ninguém olha.
    if payload.tipo_comprovante not in (None, "", *TIPOS_COMPROVANTE):
        raise HTTPException(status_code=422, detail={
            "erro": "tipo_comprovante_invalido", "aceitos": list(TIPOS_COMPROVANTE)})
    c = CriancaCreche(beneficio_id=ben.id, nome=payload.nome.strip(),
                      data_nascimento=payload.data_nascimento.strip(),
                      parentesco=payload.parentesco,
                      tipo_comprovante=payload.tipo_comprovante or None)
    db.add(c)
    registrar(db, "creche_crianca_na_admissao", ator="candidato", candidato_id=cand.id)
    db.commit()
    return _dump_crianca(c)


@router.delete("/c/{token}/creche/criancas/{crianca_id}", status_code=204)
def creche_admissao_del(token: str, crianca_id: str, db: Session = Depends(get_db)) -> None:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    c = db.get(CriancaCreche, crianca_id)
    ben = db.get(BeneficioCreche, c.beneficio_id) if c else None
    if c is None or ben is None or ben.candidato_id != cand.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    db.delete(c)
    db.commit()


@router.post("/c/{token}/creche/criancas/{crianca_id}/documento")
async def creche_admissao_doc(token: str, crianca_id: str, tipo: str, arquivo: UploadFile,
                              db: Session = Depends(get_db)) -> dict:
    from app.services.magic_link import resolver_token
    cand = resolver_token(db, token)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    c = db.get(CriancaCreche, crianca_id)
    ben = db.get(BeneficioCreche, c.beneficio_id) if c else None
    if c is None or ben is None or ben.candidato_id != cand.id:
        raise HTTPException(status_code=404, detail="crianca_nao_encontrada")
    if tipo not in ("certidao", "guarda"):
        raise HTTPException(status_code=422, detail="tipo_invalido")
    # Teto de tamanho, extensão da lista e — principalmente — `close()` do
    # spool. Esta rota é PÚBLICA e gravava qualquer coisa, de qualquer tamanho,
    # deixando o arquivo temporário no container: o que sobrava ali era
    # certidão de nascimento de criança (v2.56).
    # `EXTENSOES_COM_WORD`: a câmera guiada oferece o seletor de arquivo com
    # `.doc/.docx` (v2.61), e recusar aqui devolveria "formato não suportado"
    # para um envio que a própria tela ofereceu.
    conteudo = await ler_upload(db, arquivo, EXTENSOES_COM_WORD)
    key = _guardar_doc_crianca(ben.id, crianca_id, tipo, arquivo, conteudo)
    if tipo == "certidao":
        c.certidao_key = key
    else:
        c.guarda_key = key
    db.commit()
    return _dump_crianca(c)


# ==========================================================================
# Comprovante MENSAL de despesa (v3.02)
#
# O e-mail de ativação manda enviar, todo mês, a nota fiscal da creche (PJ) ou a
# declaração de quitação do cuidador (PF) — e até aqui não havia rota que
# recebesse isso. As regras são do Jurídico (e-mail de 18/08/2026): um por filho
# e por mês, com corte no dia 25.
#
# A lógica mora em `services/creche_envio.py`, compartilhada com a porta do RH:
# duplicá-la faria as duas divergirem na primeira mudança (v2.74).
# ==========================================================================


@router.get("/creche/sessao/{token}/competencias")
def listar_competencias(token: str, db: Session = Depends(get_db)) -> dict:
    """O que já foi entregue e o que falta, por criança.

    Devolve também a competência SUGERIDA (o mês anterior) e o prazo — quem abre
    a tela precisa saber *o que* enviar e *até quando*, sem ter que calcular.
    """
    from datetime import date as _date

    from app.models.creche_competencia import CompetenciaCreche
    from app.services import creche_competencia as regras
    from app.services.creche_envio import dump

    _, ben = _requer_sessao(token, db)
    col = db.get(Candidato, ben.candidato_id)
    posto = (db.get(PostoServico, col.posto_servico_id)
             if col and col.posto_servico_id else None)
    teto = regras.centavos(posto.valor_reembolso_creche) if posto else None

    hoje = _date.today()
    ano_sug, mes_sug = regras.competencia_anterior(hoje)
    registros = db.scalars(select(CompetenciaCreche).where(
        CompetenciaCreche.beneficio_id == ben.id).order_by(
        CompetenciaCreche.ano.desc(), CompetenciaCreche.mes.desc())).all()

    dia = ben.dia_entrega_mensal or regras.DIA_CORTE_PADRAO
    entregues = {(r.crianca_id, r.ano, r.mes) for r in registros}
    # Só as crianças DEFERIDAS geram pendência: cobrar comprovante de quem foi
    # indeferido faria a pessoa juntar documento para um direito que não existe.
    pendentes = [
        {"crianca_id": str(c.id), "crianca": c.nome,
         "competencia": regras.rotulo(ano_sug, mes_sug),
         "ano": ano_sug, "mes": mes_sug,
         "tipo_comprovante": c.tipo_comprovante}
        for c in ben.criancas
        if c.decisao != "indeferida" and (c.id, ano_sug, mes_sug) not in entregues
    ]
    return {
        "dia_corte": dia,
        "dias_para_o_corte": regras.dias_para_o_corte(dia, hoje),
        "competencia_sugerida": {"ano": ano_sug, "mes": mes_sug,
                                 "rotulo": regras.rotulo(ano_sug, mes_sug)},
        "ativo": ben.status == StatusBeneficio.ativo,
        "pendentes": pendentes,
        "competencias": [dump(r, teto) for r in registros],
    }


@router.post("/creche/sessao/{token}/competencias")
async def enviar_comprovante(token: str, crianca_id: uuid.UUID, ano: int, mes: int,
                             arquivos: list[UploadFile],
                             valor: str | None = None,
                             db: Session = Depends(get_db)) -> dict:
    """Envia o comprovante do mês. Aceita VÁRIAS folhas — viram um PDF só.

    `arquivos` é lista porque a câmera guiada devolve uma foto por folha (v2.61)
    e a declaração/nota costuma ter mais de uma. Guardar só a primeira era a
    causa do "não consigo ver se há mais de uma folha": não havia.
    """
    from app.services.creche_envio import dump, receber

    _, ben = _requer_sessao(token, db)
    partes: list[tuple[str, bytes]] = []
    for arq in arquivos:
        conteudo = await ler_upload(db, arq, EXTENSOES_COM_WORD)
        partes.append((arq.filename or "comprovante", conteudo))

    registro = receber(db, ben, crianca_id, ano, mes, partes, valor,
                       ator="colaborador")
    col = db.get(Candidato, ben.candidato_id)
    posto = (db.get(PostoServico, col.posto_servico_id)
             if col and col.posto_servico_id else None)
    from app.services.creche_competencia import centavos
    return dump(registro, centavos(posto.valor_reembolso_creche) if posto else None)
