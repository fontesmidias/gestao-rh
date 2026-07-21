import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, func
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
    # cargo_interesse (string única) mantido por compatibilidade — sincronizado
    # com o 1º item de cargos_interesse (o `converter` legado usa esta coluna).
    cargo_interesse: Mapped[str | None] = mapped_column(String(120), index=True)
    cargos_interesse: Mapped[list | None] = mapped_column(JSON)   # múltipla escolha (Forms)
    regioes: Mapped[list | None] = mapped_column(JSON)            # regiões onde pode trabalhar
    cidade: Mapped[str | None] = mapped_column(String(120))
    escolaridade: Mapped[str | None] = mapped_column(String(60))
    resumo: Mapped[str | None] = mapped_column(Text)   # experiência/apresentação
    origem: Mapped[str | None] = mapped_column(String(80))  # como soube da empresa
    # efetivo | intermitente | tanto_faz (string, não enum — simples e suficiente)
    tipo_contratacao: Mapped[str | None] = mapped_column(String(20))
    ja_trabalhou_funcao: Mapped[bool | None] = mapped_column(Boolean)
    recebe_seguro_desemprego: Mapped[bool | None] = mapped_column(Boolean)
    # aceite LGPD (obrigatório no formulário) — carimbo é a prova do consentimento
    consentimento_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # currículo (opcional): arquivo original guardado no MinIO, servido como veio
    curriculo_key: Mapped[str | None] = mapped_column(String(300))
    curriculo_nome: Mapped[str | None] = mapped_column(String(200))
    curriculo_tipo: Mapped[str | None] = mapped_column(String(100))  # content-type
    status: Mapped[StatusTalento] = mapped_column(
        Enum(StatusTalento, name="status_talento"), default=StatusTalento.novo, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
