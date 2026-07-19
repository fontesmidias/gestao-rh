"""Trava de idempotência de curta duração para ações pesadas do RH.

Mata o duplo-clique / retry do navegador / segunda aba: enquanto uma ação
(gerar dossiê, notificar, efetivar) está em andamento para um alvo, uma segunda
chamada com a MESMA chave é recusada com 409 em vez de rodar em paralelo —
evitando dois dossiês gerados juntos, dois e-mails, corrida de escrita.

Em memória (como `limite.py`): protege contra o clique-múltiplo humano, que é o
caso real. Uma trava distribuída (Redis) só seria necessária se houvesse vários
processos servindo a MESMA ação para o MESMO alvo em milissegundos — não é o
cenário do painel. A trava expira sozinha (TTL) para nunca prender um alvo se o
handler morrer no meio."""

import threading
import time
from contextlib import contextmanager

from fastapi import HTTPException

_travas: dict[str, float] = {}   # chave -> instante em que expira
_lock = threading.Lock()
_TTL_PADRAO = 120  # s: teto de segurança; a trava normal é liberada no finally


def _adquirir(chave: str, ttl: int) -> None:
    agora = time.time()
    with _lock:
        expira = _travas.get(chave)
        if expira is not None and expira > agora:
            raise HTTPException(status_code=409, detail="ja_em_processamento")
        _travas[chave] = agora + ttl
        # limpeza oportunista das travas vencidas (mantém o dict pequeno)
        if len(_travas) > 1000:
            for k, exp in list(_travas.items()):
                if exp <= agora:
                    _travas.pop(k, None)


def _liberar(chave: str) -> None:
    with _lock:
        _travas.pop(chave, None)


@contextmanager
def trava(chave: str, ttl: int = _TTL_PADRAO):
    """Adquire a trava da chave ou levanta 409 (ja_em_processamento). Libera ao
    sair do bloco, mesmo em erro."""
    _adquirir(chave, ttl)
    try:
        yield
    finally:
        _liberar(chave)


def travar_por(prefixo: str, ttl: int = _TTL_PADRAO):
    """Dependência FastAPI: trava por `{prefixo}:{candidato_id}` durante toda a
    requisição e libera no fim (mesmo em erro/return). Uso:

        dependencies=[Depends(travar_por("efetivar"))]

    no endpoint cuja rota tenha o path param `candidato_id`/`id`. Cobre todos os
    caminhos de saída sem envolver o corpo da função num `with`."""
    from fastapi import Request

    def _dep(request: Request):
        alvo = (request.path_params.get("candidato_id")
                or request.path_params.get("id")
                or request.path_params.get("cid") or "?")
        chave = f"{prefixo}:{alvo}"
        _adquirir(chave, ttl)
        try:
            yield
        finally:
            _liberar(chave)
    return _dep
