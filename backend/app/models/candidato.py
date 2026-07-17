import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
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


class PostoServico(Base):
    """Posto/contrato onde o colaborador será lotado (ex.: INFRAERO). Postos
    podem exigir documentos adicionais assinados."""

    __tablename__ = "posto_servico"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), unique=True)
    contrato_ref: Mapped[str | None] = mapped_column(String(200))
    exige_docs_infraero: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Candidato(Base):
    __tablename__ = "candidato"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    posto_servico_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id"), nullable=True)
    cargo_funcao: Mapped[str | None] = mapped_column(String(120))
    # Remuneração digitada pelo RH (texto livre: "R$ 1.500,00" ou "1500").
    # adicionais: lista de {"nome": str, "valor": str, "tipo": "reais"|"percentual"}.
    salario_base: Mapped[str | None] = mapped_column(String(60))
    adicionais: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[StatusCandidato] = mapped_column(
        Enum(StatusCandidato, name="status_candidato"), default=StatusCandidato.convidado
    )
    nome_completo: Mapped[str] = mapped_column(String(200))
    # E-mail e celular são opcionais no convite (o RH pode só copiar o link e
    # mandar por WhatsApp); o candidato completa na ficha — e o e-mail passa a
    # ser exigido lá, porque o código de assinatura chega por ele.
    email: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    celular_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    aceite_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declaracao_veracidade_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dossie_pdf_key: Mapped[str | None] = mapped_column(String(300))
    dossie_gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arquivos_expurgados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
