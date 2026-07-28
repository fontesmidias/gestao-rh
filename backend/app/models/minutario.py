"""Minutário de mensagens (v1.98, feedback 2026-07-27): modelos de mensagem
para WhatsApp/e-mail, com campos estruturados (tom, regime, salário, escala…)
que a IA usa para gerar o texto final — o RH aprova antes de enviar, nunca sai
sozinho. Reusa o catálogo `Tag` do mini-CRM (crm.py) para categorizar/filtrar
os modelos — mesma ideia de catálogo controlado, evita "Vaga"/"vaga" virarem
categorias diferentes.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MeioEnvio(str, enum.Enum):
    whatsapp = "whatsapp"
    email = "email"
    outro = "outro"


class ModeloMensagem(Base):
    """Modelo salvo pelo RH — CRUD completo. `corpo_base` é o texto de
    referência (pode ter {{marcadores}}); a geração por IA parte dele + os
    campos estruturados preenchidos na hora da composição."""

    __tablename__ = "minutario_modelo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(160))
    meio: Mapped[MeioEnvio] = mapped_column(Enum(MeioEnvio, name="minutario_meio"),
                                            default=MeioEnvio.whatsapp)
    corpo_base: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                     onupdate=func.now())


class ModeloMensagemTag(Base):
    """Vínculo N:N modelo ↔ tag do catálogo do mini-CRM (crm_tag)."""

    __tablename__ = "minutario_modelo_tag"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    modelo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("minutario_modelo.id", ondelete="CASCADE"), index=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crm_tag.id", ondelete="CASCADE"), index=True)
