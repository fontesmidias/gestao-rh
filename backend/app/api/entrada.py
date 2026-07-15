"""Portal único de retorno do candidato: CPF + perguntas de verificação (KBA).

Desenho de segurança:
- A KBA é CONVENIÊNCIA, não fortaleza: o fallback (e a segurança real) continua
  sendo a posse do e-mail cadastrado, via link mágico.
- Anti-enumeração: CPF inexistente recebe perguntas do mesmo pool e a mesma
  resposta de erro — nada revela quem está em processo de admissão.
- Bloqueio progressivo por CPF+IP após falhas repetidas; tudo na auditoria.
- O desafio é stateless: token assinado com TTL de 10 minutos.
"""

import random
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, get_settings, ip_do_cliente
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.ficha import (ContatoEmergencia, DadosPessoais,
                              DadosProfissionaisBancarios, DocumentosIdentificacao, Endereco)
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.magic_link import emitir_link
from app.services.validacao import cpf_valido

router = APIRouter(tags=["entrada-candidato"])

DESAFIO_TTL_S = 600
MAX_FALHAS = 5
BLOQUEIO_S = 15 * 60

# Falhas recentes por chave (cpf e ip). Em memória: zera no restart, mas junto
# com o TTL do desafio e a auditoria é barreira suficiente contra força bruta.
_falhas: dict[str, list[float]] = {}


def _bloqueado(chave: str) -> bool:
    agora = time.time()
    _falhas[chave] = [t for t in _falhas.get(chave, []) if agora - t < BLOQUEIO_S]
    return len(_falhas[chave]) >= MAX_FALHAS


def _registrar_falha(*chaves: str) -> None:
    for chave in chaves:
        _falhas.setdefault(chave, []).append(time.time())


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="entrada-kba")


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def _candidato_pelo_cpf(db: Session, cpf: str) -> Candidato | None:
    """O processo MAIS RECENTE daquele CPF (recontratações geram novo processo)."""
    docs = db.scalars(select(DocumentosIdentificacao)
                      .where(DocumentosIdentificacao.cpf == cpf)).all()
    candidatos = [db.get(Candidato, d.candidato_id) for d in docs]
    candidatos = [c for c in candidatos if c is not None]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.criado_em)


# Pool de perguntas: (código, enunciado, extrator da resposta correta).
def _perguntas_do_candidato(db: Session, candidato: Candidato) -> list[tuple[str, str, str]]:
    p = db.get(DadosPessoais, candidato.id)
    e = db.get(Endereco, candidato.id)
    b = db.get(DadosProfissionaisBancarios, candidato.id)
    contato = db.scalars(select(ContatoEmergencia)
                         .where(ContatoEmergencia.candidato_id == candidato.id)).first()
    pool = []
    if p and p.data_nascimento:
        pool.append(("dia_nascimento", "Qual é o DIA do seu nascimento? (só o número)",
                     str(p.data_nascimento.day)))
        pool.append(("mes_nascimento", "Qual é o MÊS do seu nascimento? (só o número)",
                     str(p.data_nascimento.month)))
    if p and p.nome_mae:
        pool.append(("nome_mae", "Qual é o PRIMEIRO NOME da sua mãe?",
                     p.nome_mae.split()[0]))
    if p and p.naturalidade_cidade:
        pool.append(("cidade_natal", "Em que cidade você nasceu?", p.naturalidade_cidade))
    if e and e.cidade:
        pool.append(("cidade_moradia", "Em que cidade você mora?", e.cidade))
    if b and b.banco:
        pool.append(("banco", "Qual é o banco da conta que você informou?", b.banco))
    if contato and contato.nome_completo:
        pool.append(("contato_emergencia",
                     "Qual é o PRIMEIRO NOME do seu contato de emergência?",
                     contato.nome_completo.split()[0]))
    return pool


# Enunciados genéricos para CPF inexistente (anti-enumeração): mesmas categorias.
_POOL_GENERICO = [
    ("nome_mae", "Qual é o PRIMEIRO NOME da sua mãe?"),
    ("dia_nascimento", "Qual é o DIA do seu nascimento? (só o número)"),
    ("mes_nascimento", "Qual é o MÊS do seu nascimento? (só o número)"),
    ("cidade_natal", "Em que cidade você nasceu?"),
    ("cidade_moradia", "Em que cidade você mora?"),
    ("banco", "Qual é o banco da conta que você informou?"),
]


class IniciarIn(BaseModel):
    cpf: str


@router.post("/entrar/iniciar")
def iniciar(payload: IniciarIn, request: Request, db: Session = Depends(get_db)) -> dict:
    cpf = "".join(c for c in payload.cpf if c.isdigit())
    if not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="cpf_invalido")
    ip = ip_do_cliente(request) or "-"
    if _bloqueado(f"cpf:{cpf}") or _bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")

    candidato = _candidato_pelo_cpf(db, cpf)
    pool = _perguntas_do_candidato(db, candidato) if candidato else []

    if len(pool) >= 2:
        escolhidas = random.sample(pool, 2)
        perguntas = [{"codigo": c, "pergunta": q} for c, q, _ in escolhidas]
        gabarito = {c: _normalizar(resp) for c, _, resp in escolhidas}
    else:
        # CPF inexistente OU candidato sem dados suficientes: perguntas genéricas
        # com gabarito impossível — a resposta final é a mesma ("não confirmado"),
        # e o fallback por e-mail continua disponível. Nada é revelado.
        escolhidas = random.sample(_POOL_GENERICO, 2)
        perguntas = [{"codigo": c, "pergunta": q} for c, q in escolhidas]
        gabarito = {c: "__impossivel__" for c, _ in escolhidas}

    token = _serializer().dumps({"cpf": cpf, "gabarito": gabarito})
    return {"desafio": token, "perguntas": perguntas}


class ResponderIn(BaseModel):
    desafio: str
    respostas: dict[str, str]


@router.post("/entrar/responder")
def responder(payload: ResponderIn, request: Request, db: Session = Depends(get_db)) -> dict:
    ip = ip_do_cliente(request) or "-"
    try:
        dados = _serializer().loads(payload.desafio, max_age=DESAFIO_TTL_S)
    except BadSignature:
        raise HTTPException(status_code=422, detail="desafio_expirado")
    cpf = dados["cpf"]
    if _bloqueado(f"cpf:{cpf}") or _bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")

    gabarito = dados["gabarito"]
    ok = (set(payload.respostas) == set(gabarito) and all(
        _normalizar(payload.respostas.get(c, "")) == resp and resp != "__impossivel__"
        for c, resp in gabarito.items()
    ))
    if not ok:
        _registrar_falha(f"cpf:{cpf}", f"ip:{ip}")
        registrar(db, "entrada_kba_falhou", ator="candidato",
                  detalhe={"cpf_final": cpf[-4:], "ip": ip})
        db.commit()
        # Resposta uniforme: não revela se o CPF existe nem qual pergunta errou.
        raise HTTPException(status_code=422, detail="nao_confirmado")

    candidato = _candidato_pelo_cpf(db, cpf)
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "entrada_kba_ok", ator="candidato", candidato_id=candidato.id,
              detalhe={"ip": ip})
    db.commit()
    return {"link": link}


class LinkEmailIn(BaseModel):
    cpf: str


@router.post("/entrar/link-email", status_code=204)
def link_por_email(payload: LinkEmailIn, request: Request,
                   db: Session = Depends(get_db)) -> None:
    """Fallback: envia um novo link mágico ao e-mail cadastrado. Sempre 204 —
    não revela se o CPF existe."""
    cpf = "".join(c for c in payload.cpf if c.isdigit())
    ip = ip_do_cliente(request) or "-"
    if _bloqueado(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
    candidato = _candidato_pelo_cpf(db, cpf)
    registrar(db, "entrada_link_email", ator="candidato",
              detalhe={"cpf_final": cpf[-4:] if cpf else "-", "ip": ip,
                       "encontrado": candidato is not None})
    db.commit()
    if candidato is None:
        return
    link = emitir_link(db, candidato, base_url_publica(request))
    db.commit()
    enviar_email(
        candidato.email,
        "🌱 Green House — seu link de acesso à admissão",
        f"Olá, {candidato.nome_completo.split()[0].title()}!\n\n"
        f"Você pediu um novo acesso à sua admissão. Use o link abaixo:\n{link}\n\n"
        "Se não foi você, ignore esta mensagem.\n",
        html_moderno(
            "Seu link de acesso",
            [
                f"Olá, <strong>{candidato.nome_completo.split()[0].title()}</strong>!",
                "Você pediu um novo acesso à sua admissão pelo portal. "
                "Toque no botão para continuar de onde parou.",
                "Se não foi você quem pediu, ignore esta mensagem.",
            ],
            botao_texto="Continuar minha admissão",
            botao_url=link,
        ),
    )
