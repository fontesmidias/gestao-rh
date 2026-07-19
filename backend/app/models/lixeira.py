"""Lixeira universal: snapshot de registros excluídos pelo RH.

Boas práticas de manutenção de dados inativados (feedback de campo
2026-07-18): nada some de verdade na hora — o registro vira um snapshot JSON
aqui, restaurável pelo painel, e só é expurgado de fato após o prazo de
retenção (padrão 60 dias, configurável em Configurações)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ItemLixeira(Base):
    __tablename__ = "item_lixeira"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    entidade: Mapped[str] = mapped_column(String(40), index=True)  # ex.: "posto", "modelo_documento"
    entidade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rotulo: Mapped[str] = mapped_column(String(200))               # nome legível no painel
    dados: Mapped[dict] = mapped_column(JSON)                      # snapshot completo (colunas)
    ator: Mapped[str | None] = mapped_column(String(200))          # e-mail de quem excluiu
    apagado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    restaurado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
