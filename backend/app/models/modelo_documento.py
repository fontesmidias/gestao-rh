import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EscopoModelo(str, enum.Enum):
    """A quem o modelo de documento se aplica."""
    avulso = "avulso"            # disponível para qualquer colaborador
    cargo = "cargo"             # colaboradores de um cargo específico
    posto = "posto"             # colaboradores de um posto de serviço
    colaborador = "colaborador"  # um colaborador específico


class ModeloDocumento(Base):
    """Documento criado pelo RH no painel (layout timbrado padrão), com
    variáveis dinâmicas ({{nome}}, {{cargo}}…) preenchidas no momento de gerar
    o PDF para um colaborador. Vinculável a cargo, posto ou colaborador."""

    __tablename__ = "modelo_documento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(200))
    corpo: Mapped[str] = mapped_column(Text)  # texto com {{placeholders}}
    escopo: Mapped[EscopoModelo] = mapped_column(
        Enum(EscopoModelo, name="escopo_modelo"), default=EscopoModelo.avulso)
    cargo_alvo: Mapped[str | None] = mapped_column(String(120))
    posto_alvo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id"), nullable=True)
    candidato_alvo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id"), nullable=True)
    # Comportamento ao gerar/enviar para uma pessoa
    enviar_por_email: Mapped[bool] = mapped_column(Boolean, default=False)
    exige_assinatura: Mapped[bool] = mapped_column(Boolean, default=False)
    # Papel com que o colaborador assina (dos papéis de Configurações → Assinaturas)
    papel_assinatura: Mapped[str | None] = mapped_column(String(60))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now())


class PapelAssinatura(Base):
    """Papéis/qualidades com que alguém assina um documento (Contratado(a),
    Contratante, Testemunha, Validador(a)…). Compõem o manifesto de assinatura.
    A `ordem` prepara o terreno para fluxos com vários signatários em sequência."""

    __tablename__ = "papel_assinatura"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(60), unique=True)
    descricao: Mapped[str | None] = mapped_column(String(300))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
