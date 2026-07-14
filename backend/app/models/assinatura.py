import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentoAssinavel(str, enum.Enum):
    ficha_cadastro = "ficha_cadastro"
    ficha_emergencia = "ficha_emergencia"
    termo_vt = "termo_vt"


class Assinatura(Base):
    """Assinatura eletrônica simples (Lei 14.063/2020) com trilha de evidências."""

    __tablename__ = "assinatura"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    documento: Mapped[DocumentoAssinavel] = mapped_column(
        Enum(DocumentoAssinavel, name="documento_assinavel")
    )
    pdf_key: Mapped[str | None] = mapped_column(String(300))
    hash_sha256: Mapped[str | None] = mapped_column(String(64))
    otp_hash: Mapped[str | None] = mapped_column(String(64))
    otp_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_tentativas: Mapped[int] = mapped_column(default=0)
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
