"""Serviço da lixeira: snapshot na exclusão, restauração e expurgo por prazo."""

import enum
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lixeira import ItemLixeira
from app.services.config_dinamica import ler_config

DIAS_PADRAO = 60


def _jsonavel(v):
    if isinstance(v, (uuid.UUID,)):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, enum.Enum):
        return v.value
    return v


def snapshot(obj) -> dict:
    """Snapshot JSON de todas as colunas do registro."""
    return {c.name: _jsonavel(getattr(obj, c.name)) for c in obj.__table__.columns}


def mandar_para_lixeira(db: Session, obj, entidade: str, rotulo: str,
                        ator: str | None) -> ItemLixeira:
    """Guarda o snapshot ANTES do delete (o caller faz o db.delete/commit)."""
    item = ItemLixeira(entidade=entidade, entidade_id=obj.id, rotulo=rotulo[:200],
                       dados=snapshot(obj), ator=ator)
    db.add(item)
    return item


def dias_retencao(db: Session) -> int:
    cfg = ler_config(db, ("lixeira_dias",))
    try:
        return max(1, int(cfg.get("lixeira_dias") or DIAS_PADRAO))
    except ValueError:
        return DIAS_PADRAO


def expurgar_vencidos(db: Session) -> int:
    """Remove da lixeira o que passou do prazo de retenção (aí sim, definitivo)."""
    limite = datetime.now(timezone.utc) - timedelta(days=dias_retencao(db))
    vencidos = db.scalars(select(ItemLixeira)
                          .where(ItemLixeira.apagado_em < limite)).all()
    for item in vencidos:
        db.delete(item)
    return len(vencidos)
