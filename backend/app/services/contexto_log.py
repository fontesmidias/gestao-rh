"""Contexto que acompanha CADA linha de log da mesma requisição (v2.41).

Feedback do Bruno em 2026-08-01: *"achei muito bom o layout, apenas pobre de
tipos de informações que são registradas nos logs, acho que poderiam ser muito
mais informações, para que pudesse possibilitar investigações verdadeiras
mesmo"*.

O que faltava não era volume — era **poder ligar uma linha à outra**. O log
registrava "POST /api/c/ab12*** status=200" e, três linhas abaixo, um erro de
storage: nada dizia que os dois eram a mesma pessoa, na mesma ação, no mesmo
segundo. Investigar virava adivinhação com carimbo de hora.

Agora toda linha carrega:

* `req=<8 chars>` — o mesmo identificador para tudo que acontece dentro de uma
  requisição. É o que permite pegar um erro e ver o que veio antes e depois
  dele, mesmo com dez pessoas usando o sistema ao mesmo tempo.
* `ator=<quem>` — o e-mail do usuário do RH, ou `candidato:<primeiro nome>`
  para quem entrou por link mágico. Sem isso, "alguém reprovou o documento"
  não tem dono.

## LGPD

O ator é o MENOR identificador que responde à pergunta "quem foi": e-mail para
o RH (que é usuário do sistema, com login) e **primeiro nome** para o
candidato — nunca o token do link, que é credencial, nem o CPF, que já aparece
demais no log. `mascarar` corta qualquer coisa longa demais para não virar
depósito de dado.

## Por que `contextvars`, e não um parâmetro

O log acontece em dezenas de lugares que não têm — nem deveriam ter — acesso à
requisição: `storage.py`, `email.py`, um serviço qualquer no meio da pilha.
Passar o identificador por parâmetro obrigaria a mudar todas as assinaturas do
projeto, e quem esquecesse deixaria um buraco justamente no lugar onde o
defeito aparecesse. O contexto viaja sozinho, inclusive entre `await`s.
"""

from __future__ import annotations

import contextvars
import logging
import uuid

_REQUISICAO: contextvars.ContextVar[str] = contextvars.ContextVar("req_id", default="")
_ATOR: contextvars.ContextVar[str] = contextvars.ContextVar("ator", default="")


def novo_id() -> str:
    """Identificador curto da requisição. 8 caracteres bastam para separar o
    que acontece ao mesmo tempo, e cabem na linha sem atrapalhar a leitura."""
    return uuid.uuid4().hex[:8]


def mascarar(valor: str | None, limite: int = 60) -> str:
    """Corta e limpa o que vai para a linha de log — nada de campo livre
    entrando inteiro num arquivo que é lido, baixado e enviado por e-mail."""
    if not valor:
        return ""
    texto = " ".join(str(valor).split())
    return texto[:limite]


def definir(req_id: str | None = None, ator: str | None = None) -> str:
    """Marca o contexto da requisição atual; devolve o id em uso."""
    rid = req_id or novo_id()
    _REQUISICAO.set(rid)
    if ator is not None:
        _ATOR.set(mascarar(ator))
    return rid


def definir_ator(ator: str | None) -> None:
    """Chamado quando a identidade só é conhecida DEPOIS do início (resolver o
    token do link mágico, autenticar o RH)."""
    _ATOR.set(mascarar(ator))


def atual() -> tuple[str, str]:
    return _REQUISICAO.get(), _ATOR.get()


class FiltroContexto(logging.Filter):
    """Injeta `req` e `ator` em toda linha, sem que ninguém precise passá-los.

    Nunca levanta: um log que quebra a requisição que estava tentando
    documentar seria o pior dos mundos (mesma regra do `avisar()`).
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            rid, ator = atual()
            record.req = rid or "-"
            record.ator = ator or "-"
        except Exception:
            record.req = "-"
            record.ator = "-"
        return True
