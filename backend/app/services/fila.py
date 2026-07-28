"""Fila de tarefas em background (Redis + RQ).

O ecossistema já tinha Redis e um container `worker` rodando
`rq worker --url $REDIS_URL default` desde a v1.83 — mas ninguém nunca
enfileirou nada nele: os workers existentes (expurgo, avisar_vencimentos,
expirar_roteiros) são agendados por cron, não passam pela fila. Esta camada
finalmente usa a infra que já estava de pé e ociosa.

Primeiro uso (v2.00): ranqueamento do Match de Vagas e extração de texto de
currículo. Motivo — o RH precisa continuar usando o sistema enquanto a
análise roda (131 talentos levam minutos), e o nginx corta qualquer request
acima de 60s (`location /api/` usa o default; a exceção de 600s existe só
para /api/rh/arquivo/lote).

Se o Redis estiver fora, `enfileirar` levanta — o chamador decide (a rota do
match devolve 503 com mensagem honesta em vez de fingir que enfileirou)."""

import logging

from redis import Redis
from rq import Queue

from app.core.config import get_settings

log = logging.getLogger(__name__)

NOME_FILA = "default"          # a mesma que o container `worker` escuta
_TIMEOUT_TAREFA = 60 * 60      # 1h: ranqueamento de centenas de talentos com
                               # espera de cota pode ser demorado, e tudo bem


def _conexao() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def enfileirar(funcao, *args, timeout: int | None = None, **kwargs):
    """Põe a tarefa na fila e devolve o job. NÃO engole erro de conexão — se
    o Redis estiver fora, o RH precisa saber que o trabalho não foi aceito."""
    fila = Queue(NOME_FILA, connection=_conexao(),
                 default_timeout=timeout or _TIMEOUT_TAREFA)
    job = fila.enqueue(funcao, *args, **kwargs)
    log.info("Tarefa enfileirada: %s (job=%s)", getattr(funcao, "__name__", funcao), job.id)
    return job


def fila_disponivel() -> bool:
    """Ping no Redis — usado para dizer ao RH que o processamento em segundo
    plano está fora do ar, em vez de deixar o botão sem efeito."""
    try:
        return bool(_conexao().ping())
    except Exception as exc:
        log.warning("Redis indisponível (%s).", type(exc).__name__)
        return False
