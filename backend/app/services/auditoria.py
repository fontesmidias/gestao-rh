"""Registro de eventos de auditoria. Nunca derruba a operação principal."""

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.evento import EventoAuditoria

log = logging.getLogger("auditoria")


def registrar(
    db: Session,
    acao: str,
    ator: str = "sistema",
    candidato_id: uuid.UUID | None = None,
    ator_detalhe: str | None = None,
    detalhe: dict | None = None,
) -> None:
    try:
        db.add(EventoAuditoria(
            candidato_id=candidato_id, ator=ator, ator_detalhe=ator_detalhe,
            acao=acao, detalhe=detalhe,
        ))
        db.flush()
        log.info("evento=%s ator=%s candidato=%s detalhe=%s", acao, ator, candidato_id, detalhe)
    except Exception:
        log.exception("Falha ao registrar evento %s", acao)
