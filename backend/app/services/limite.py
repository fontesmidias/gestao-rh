"""Limitação de tentativas (rate limiting) para endpoints sensíveis.

Janela deslizante em memória, no padrão que já protegia o portal de retorno
(`api/entrada.py`): zera no restart do container, mas combinada com TTLs curtos
dos códigos e a auditoria é barreira suficiente contra força bruta de senha,
código 2FA e disparo de e-mails. Chaves típicas: "login:ip:<ip>",
"2fa:<token>", "reset:ip:<ip>"."""

import threading
import time

from fastapi import HTTPException

_tentativas: dict[str, list[float]] = {}
_trava = threading.Lock()
_MAX_CHAVES = 50_000  # teto de memória; ao passar, descarta as janelas velhas


def permitir(chave: str, maximo: int, janela_s: int) -> bool:
    """Registra uma tentativa e diz se ela ainda cabe na janela."""
    agora = time.time()
    with _trava:
        if len(_tentativas) > _MAX_CHAVES:
            _tentativas.clear()
        recentes = [t for t in _tentativas.get(chave, []) if agora - t < janela_s]
        ok = len(recentes) < maximo
        if ok:
            recentes.append(agora)
        _tentativas[chave] = recentes
        return ok


def exigir(chave: str, maximo: int, janela_s: int) -> None:
    """Levanta 429 (muitas_tentativas) quando a janela estoura."""
    if not permitir(chave, maximo, janela_s):
        raise HTTPException(status_code=429, detail="muitas_tentativas")
