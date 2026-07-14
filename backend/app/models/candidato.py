import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusCandidato(str, enum.Enum):
    convidado = "convidado"
    preenchendo = "preenchendo"
    docs_pendentes = "docs_pendentes"
    aguardando_assinatura = "aguardando_assinatura"
    envio_concluido = "envio_concluido"
    em_revisao = "em_revisao"
    aprovado = "aprovado"
    reprovado_pendencias = "reprovado_pendencias"
    expurgado = "expurgado"


class Candidato(Base):
    __tablename__ = "candidato"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[StatusCandidato] = mapped_column(
        Enum(StatusCandidato, name="status_candidato"), default=StatusCandidato.convidado
    )
    nome_completo: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), index=True)
    celular_whatsapp: Mapped[str] = mapped_column(String(20))
    aceite_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declaracao_veracidade_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    acessos: Mapped[list["AcessoMagico"]] = relationship(back_populates="candidato")


class AcessoMagico(Base):
    __tablename__ = "acesso_magico"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    # Apenas o hash do token é persistido; o token em claro vai só no link enviado.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revogado: Mapped[bool] = mapped_column(default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidato: Mapped[Candidato] = relationship(back_populates="acessos")
