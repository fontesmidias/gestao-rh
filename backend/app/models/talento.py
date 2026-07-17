import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusTalento(str, enum.Enum):
    novo = "novo"
    em_analise = "em_analise"
    convertido = "convertido"       # virou candidato (admissão iniciada)
    arquivado = "arquivado"


class Talento(Base):
    """Cadastro do Banco de Talentos: captação de interessados ANTES de haver
    vaga/convite. O RH filtra, tria e, ao decidir contratar, converte o
    talento em candidato (migrando os dados já preenchidos)."""

    __tablename__ = "talento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    telefone: Mapped[str | None] = mapped_column(String(20))
    cargo_interesse: Mapped[str | None] = mapped_column(String(120), index=True)
    cidade: Mapped[str | None] = mapped_column(String(120))
    escolaridade: Mapped[str | None] = mapped_column(String(60))
    resumo: Mapped[str | None] = mapped_column(Text)   # experiência/apresentação
    origem: Mapped[str | None] = mapped_column(String(80))  # como soube da empresa
    status: Mapped[StatusTalento] = mapped_column(
        Enum(StatusTalento, name="status_talento"), default=StatusTalento.novo, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
