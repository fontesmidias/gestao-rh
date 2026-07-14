import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EventoAuditoria(Base):
    """Trilha de auditoria: quem fez o quê, quando — consultável pelo painel do RH."""

    __tablename__ = "evento_auditoria"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id"), index=True
    )
    ator: Mapped[str] = mapped_column(String(20))  # candidato | rh | sistema
    ator_detalhe: Mapped[str | None] = mapped_column(String(200))  # e-mail do RH etc.
    acao: Mapped[str] = mapped_column(String(60), index=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
