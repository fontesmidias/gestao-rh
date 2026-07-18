"""Benefício Reembolso-Creche (IN SEGES/MGI nº 147/2026, Decreto 12.926/2026).

Um colaborador adere ao benefício pelo link público de levantamento e informa
as crianças que lhe dão direito. O RH revisa e ativa. Ao ativar, o colaborador
passa a receber, mensalmente, orientações e prazos para a documentação de
despesa (declaração de pessoa física OU nota fiscal de creche PJ)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class StatusBeneficio(str, enum.Enum):
    # o colaborador ainda está preenchendo o levantamento
    levantamento = "levantamento"
    # enviou dados + docs; aguarda o RH revisar
    em_analise = "em_analise"
    # RH aprovou, mas depende de termo aditivo/repactuação do contrato (IN 147)
    aguardando_repactuacao = "aguardando_repactuacao"
    # benefício em pagamento
    ativo = "ativo"
    # suspenso (criança completou 6 anos, pendência) ou encerrado (desligamento)
    suspenso = "suspenso"
    encerrado = "encerrado"
    # RH recusou o pedido
    indeferido = "indeferido"


class BeneficioCreche(Base):
    """A adesão de um colaborador ao reembolso-creche (uma por colaborador)."""

    __tablename__ = "beneficio_creche"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id"), unique=True, index=True)
    status: Mapped[StatusBeneficio] = mapped_column(
        Enum(StatusBeneficio, name="status_beneficio"), default=StatusBeneficio.levantamento)
    # e-mail confirmado no 2FA do link público (pode diferir do e-mail do cadastro)
    email_confirmado: Mapped[str | None] = mapped_column(String(200))
    email_confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    telefone: Mapped[str | None] = mapped_column(String(20))
    # o colaborador conferiu e confirmou os dados pré-preenchidos da base
    dados_conferidos_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requerimento_assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # decisão do RH
    revisado_por: Mapped[str | None] = mapped_column(String(200))
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_indeferimento: Mapped[str | None] = mapped_column(String(400))
    ativado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # dossiê do benefício (separado do admissional)
    dossie_pdf_key: Mapped[str | None] = mapped_column(String(300))
    dossie_gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # prazo mensal para entrega da documentação de despesa — dia do mês (1-31);
    # editável pelo RH em massa ou individualmente. Default 5.
    dia_entrega_mensal: Mapped[int] = mapped_column(default=5)
    # valor do reembolso vigente para este colaborador (copiado do posto na
    # ativação; pode divergir se o contrato repactuar depois).
    valor_reembolso: Mapped[str | None] = mapped_column(String(30))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    criancas: Mapped[list["CriancaCreche"]] = relationship(
        back_populates="beneficio", cascade="all, delete-orphan")


class CriancaCreche(Base):
    """Criança que dá direito ao benefício (filho, enteado ou guarda judicial)."""

    __tablename__ = "crianca_creche"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    beneficio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("beneficio_creche.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    data_nascimento: Mapped[str] = mapped_column(String(10))  # dd/mm/aaaa
    parentesco: Mapped[str] = mapped_column(String(30))  # filho | enteado | guarda
    # chaves dos arquivos no storage (certidão sempre; guarda quando aplicável)
    certidao_key: Mapped[str | None] = mapped_column(String(300))
    guarda_key: Mapped[str | None] = mapped_column(String(300))
    # tipo de comprovante de despesa que a família usará (declaração PF ou NF PJ)
    tipo_comprovante: Mapped[str | None] = mapped_column(String(20))  # declaracao | nota_fiscal
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    beneficio: Mapped[BeneficioCreche] = relationship(back_populates="criancas")


class AcessoCreche(Base):
    """Token de sessão do link público de levantamento (como o link mágico do
    candidato, mas para o benefício). Guardamos só o hash."""

    __tablename__ = "acesso_creche"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    beneficio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("beneficio_creche.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # código 2FA (hash) enviado ao e-mail para confirmar identidade
    codigo_hash: Mapped[str | None] = mapped_column(String(64))
    codigo_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
