"""KBA (Knowledge-Based Authentication) compartilhada.

Desafio de identidade por perguntas que, em tese, só a própria pessoa saberia
responder — usado tanto no retorno do candidato à admissão (`api/entrada.py`)
quanto no gate do Reembolso-Creche para quem não tem e-mail cadastrado
(`api/creche_publico.py`).

Desenho de segurança (idêntico ao de `entrada.py`, agora centralizado):
- A KBA é CONVENIÊNCIA, não fortaleza: resiste a chute casual, não a um atacante
  que já conhece os dados da vítima. Por isso o desfecho sempre tem um segundo
  fator adiante (link mágico ou código no e-mail).
- Anti-enumeração: CPF inexistente (ou sem dados suficientes) recebe perguntas do
  MESMO pool genérico, com gabarito impossível, e a MESMA resposta de erro. Nada
  na resposta revela se o CPF existe na base.
- Bloqueio progressivo por CPF+IP após falhas repetidas (em memória: zera no
  restart do container, mas junto com o TTL curto do desafio e a auditoria é
  barreira suficiente contra força bruta).
- O desafio é stateless: token assinado (itsdangerous) com TTL curto.
"""

import random
import time
import unicodedata

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.candidato import Candidato
from app.models.ficha import (ContatoEmergencia, DadosPessoais,
                             DadosProfissionaisBancarios, Endereco)

DESAFIO_TTL_S = 600
MAX_FALHAS = 5
BLOQUEIO_S = 15 * 60

# Falhas recentes por chave (cpf e ip). Compartilhado entre os fluxos que usam
# a KBA — um atacante bloqueado num fluxo fica bloqueado no outro.
_falhas: dict[str, list[float]] = {}


def bloqueado(chave: str) -> bool:
    agora = time.time()
    _falhas[chave] = [t for t in _falhas.get(chave, []) if agora - t < BLOQUEIO_S]
    return len(_falhas[chave]) >= MAX_FALHAS


def registrar_falha(*chaves: str) -> None:
    for chave in chaves:
        _falhas.setdefault(chave, []).append(time.time())


def serializer(salt: str) -> URLSafeTimedSerializer:
    """Serializer assinado por `salt` — cada fluxo usa o seu (um token de um
    fluxo não vale no outro)."""
    return URLSafeTimedSerializer(get_settings().secret_key, salt=salt)


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sem_acento.lower() if c.isalnum())


def perguntas_do_candidato(db: Session, candidato: Candidato) -> list[tuple[str, str, str]]:
    """Pool de perguntas (código, enunciado, resposta correta).

    Começa pelos dados IMUTÁVEIS NATIVOS do próprio Candidato (nascimento e nome)
    — que existem inclusive para quem foi IMPORTADO do Tirvu e nunca preencheu a
    ficha de admissão (feedback 2026-07-22: antes o pool vinha só das fichas, e o
    colaborador importado — a maioria — nunca tinha perguntas suficientes e caía
    no gabarito impossível, sem conseguir entrar). Depois complementa com os
    dados de ficha, quando existirem."""
    pool: list[tuple[str, str, str]] = []

    # --- imutáveis nativos (valem para importado E para quem fez a ficha) ---
    # data_nascimento nativa é string "dd/mm/aaaa"
    nasc = (candidato.data_nascimento or "").strip()
    if len(nasc) == 10 and nasc[2] == "/" and nasc[5] == "/":
        dia, mes = nasc[:2], nasc[3:5]
        pool.append(("dia_nascimento", "Qual é o DIA do seu nascimento? (só o número)",
                     str(int(dia))))
        pool.append(("mes_nascimento", "Qual é o MÊS do seu nascimento? (só o número)",
                     str(int(mes))))
    partes_nome = [x for x in (candidato.nome_completo or "").split() if len(x) > 2]
    if len(partes_nome) >= 2:
        # um SOBRENAME (o último com >2 letras — evita "de"/"da"/"do")
        pool.append(("sobrenome", "Qual é o seu ÚLTIMO sobrenome?", partes_nome[-1]))

    # --- complementos de ficha (só quem passou pela admissão daqui tem) ---
    p = db.get(DadosPessoais, candidato.id)
    e = db.get(Endereco, candidato.id)
    b = db.get(DadosProfissionaisBancarios, candidato.id)
    contato = db.scalars(select(ContatoEmergencia)
                         .where(ContatoEmergencia.candidato_id == candidato.id)).first()
    # nascimento da ficha só se a nativa faltou (evita pergunta duplicada)
    if not any(c == "dia_nascimento" for c, _, _ in pool) and p and p.data_nascimento:
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


# Enunciados genéricos para CPF inexistente (anti-enumeração): mesmas categorias
# que as perguntas reais, para não revelar nada pela forma da pergunta.
POOL_GENERICO = [
    ("sobrenome", "Qual é o seu ÚLTIMO sobrenome?"),
    ("nome_mae", "Qual é o PRIMEIRO NOME da sua mãe?"),
    ("dia_nascimento", "Qual é o DIA do seu nascimento? (só o número)"),
    ("mes_nascimento", "Qual é o MÊS do seu nascimento? (só o número)"),
    ("cidade_natal", "Em que cidade você nasceu?"),
    ("cidade_moradia", "Em que cidade você mora?"),
    ("banco", "Qual é o banco da conta que você informou?"),
]


def montar_desafio(db: Session, candidato: Candidato | None,
                   salt: str, extra_payload: dict | None = None) -> dict:
    """Monta um desafio de 2 perguntas + token assinado. Se o candidato não
    existe ou não tem dados suficientes, usa o pool genérico com gabarito
    impossível — a resposta final é a mesma ("não confirmado"), nada é revelado.

    `extra_payload` é embutido no token (ex.: o cpf) para o `responder` recuperar.
    """
    pool = perguntas_do_candidato(db, candidato) if candidato else []
    if len(pool) >= 2:
        escolhidas = random.sample(pool, 2)
        perguntas = [{"codigo": c, "pergunta": q} for c, q, _ in escolhidas]
        gabarito = {c: normalizar(resp) for c, _, resp in escolhidas}
    else:
        escolhidas_g = random.sample(POOL_GENERICO, 2)
        perguntas = [{"codigo": c, "pergunta": q} for c, q in escolhidas_g]
        gabarito = {c: "__impossivel__" for c, _ in escolhidas_g}
    payload = {"gabarito": gabarito, **(extra_payload or {})}
    token = serializer(salt).dumps(payload)
    return {"desafio": token, "perguntas": perguntas}


def conferir_respostas(gabarito: dict, respostas: dict) -> bool:
    """True se TODAS as respostas batem com o gabarito e nenhuma é impossível."""
    return (set(respostas) == set(gabarito) and all(
        normalizar(respostas.get(c, "")) == resp and resp != "__impossivel__"
        for c, resp in gabarito.items()
    ))
