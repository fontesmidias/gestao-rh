"""Vigia da telemetria: roda as regras de alerta e avisa quem estiver na matriz.

Executa a cada 15 minutos (agendado no compose, junto do worker de expurgo). A
cadência foi escolhida pelo Bruno: rápido o bastante para saber antes de o
candidato ligar, espaçado o bastante para os avisos chegarem agrupados.

Rode à mão: python -m app.workers.alertas_telemetria
"""

import logging

from sqlalchemy import inspect

from app.core.db import SessionLocal
from app.services.alertas import avaliar

log = logging.getLogger(__name__)


def rodar() -> int:
    """Avalia as regras e envia o que disparou. Devolve o nº de disparos."""
    with SessionLocal() as db:
        try:
            # O worker sobe em paralelo com a API, que é quem roda as
            # migrations no entrypoint. Numa atualização que traga tabela nova,
            # a primeira volta do laço encontra o banco ainda sem ela — barulho
            # de partida, não defeito. Registrar como ERRO faria o log gritar a
            # cada deploy e ensinaria a ignorar o log, que é como um erro de
            # verdade passa despercebido (visto na subida da v2.25).
            if not inspect(db.get_bind()).has_table("regra_alerta"):
                log.info("tabela de regras ainda não existe (migrations em curso); "
                         "tentando de novo na próxima volta")
                return 0

            disparos = avaliar(db, enviar=True)
            db.commit()
            for d in disparos:
                log.info("alerta disparado: %s (%s item(ns))", d["regra"], d["total"])
            return len(disparos)
        except Exception:
            # O vigia nunca pode derrubar o container: se ele morrer em laço,
            # perdemos o alerta E o expurgo que roda no mesmo agendamento.
            log.exception("falha ao avaliar os alertas de telemetria")
            db.rollback()
            return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Alertas disparados: {rodar()}")
