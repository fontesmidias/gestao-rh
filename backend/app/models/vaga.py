"""Vaga (v1.99, Match de Vagas × Banco de Talentos): descrição da vaga que o
RH cadastra para ranquear os talentos aderentes. Ver services/match_vagas.py
e services/anti_prompt_injection.py (o currículo do talento é entrada
hostil, nunca instrução)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Vaga(Base):
    __tablename__ = "vaga"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(160))
    descricao: Mapped[str] = mapped_column(Text)
    requisitos_obrigatorios: Mapped[str | None] = mapped_column(Text)
    requisitos_desejaveis: Mapped[str | None] = mapped_column(Text)
    cargo: Mapped[str | None] = mapped_column(String(120))
    regiao: Mapped[str | None] = mapped_column(String(120))
    regime: Mapped[str | None] = mapped_column(String(20))  # efetivo | intermitente | tanto_faz
    salario_min: Mapped[str | None] = mapped_column(String(30))
    salario_max: Mapped[str | None] = mapped_column(String(30))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
