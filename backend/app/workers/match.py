"""Tarefas de background do Match de Vagas (fila RQ — v2.00).

Estas funções são o que o container `worker` executa. Elas precisam ser
importáveis por caminho (o RQ serializa a referência da função, não o
código), por isso ficam num módulo estável e com assinatura simples
(só ids, nada de objetos do SQLAlchemy).

O ranqueamento vive aqui porque o RH precisa continuar usando o sistema
enquanto a análise roda: 131 talentos levam minutos, e o nginx corta
qualquer request acima de 60s.
"""

import logging

log = logging.getLogger(__name__)


def ranquear(processamento_id: str, reanalisar: bool = False) -> dict:
    """Executa um ranqueamento inteiro. Chamado pela fila."""
    from app.services.match_vagas import executar_processamento
    log.info("Worker: iniciando ranqueamento %s (reanalisar=%s).",
             processamento_id, reanalisar)
    return executar_processamento(processamento_id, reanalisar=reanalisar)


def indexar_curriculo(talento_id: str) -> dict:
    """Extrai o texto do currículo de um talento (no upload)."""
    from app.services.curriculo_indexacao import indexar_talento
    return indexar_talento(talento_id)


def backfill_curriculos(limite: int | None = None) -> dict:
    """Indexa currículos que já estavam na base antes da v2.00."""
    from app.services.curriculo_indexacao import backfill
    return backfill(limite=limite)
