import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TipoDocumento(str, enum.Enum):
    foto_3x4 = "foto_3x4"
    rg = "rg"
    cpf_doc = "cpf_doc"
    ctps_digital = "ctps_digital"
    pis_comprovante = "pis_comprovante"
    titulo_eleitor_doc = "titulo_eleitor_doc"
    reservista = "reservista"
    habilitacao_prof = "habilitacao_prof"
    laudo_pcd = "laudo_pcd"
    comp_endereco = "comp_endereco"
    comp_escolaridade = "comp_escolaridade"
    diplomas = "diplomas"
    nada_consta_eleitoral = "nada_consta_eleitoral"
    nada_consta_criminal = "nada_consta_criminal"
    cert_casamento = "cert_casamento"
    cert_nascimento_dep = "cert_nascimento_dep"
    cartao_vacina_dep = "cartao_vacina_dep"
    declaracao_escolar_dep = "declaracao_escolar_dep"
    cartao_vt = "cartao_vt"


class StatusSlot(str, enum.Enum):
    pendente = "pendente"
    enviado = "enviado"
    aprovado = "aprovado"
    rejeitado = "rejeitado"
    dispensado = "dispensado"


class MotivoRejeicao(str, enum.Enum):
    ilegivel = "ilegivel"
    doc_errado = "doc_errado"
    vencido = "vencido"
    incompleto = "incompleto"
    outro = "outro"


class SlotDocumento(Base):
    __tablename__ = "slot_documento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    tipo: Mapped[TipoDocumento] = mapped_column(Enum(TipoDocumento, name="tipo_documento"))
    dependente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dependente.id"))
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[StatusSlot] = mapped_column(
        Enum(StatusSlot, name="status_slot"), default=StatusSlot.pendente
    )
    motivo_rejeicao: Mapped[MotivoRejeicao | None] = mapped_column(
        Enum(MotivoRejeicao, name="motivo_rejeicao")
    )
    motivo_rejeicao_obs: Mapped[str | None] = mapped_column(Text)
    arquivo_original_key: Mapped[str | None] = mapped_column(String(300))
    arquivo_pdf_key: Mapped[str | None] = mapped_column(String(300))
    paginas: Mapped[int | None] = mapped_column(SmallInteger)
    # 'rh' quando o documento chegou fora do sistema (WhatsApp, presencial…) e
    # o RH o inseriu manualmente — etiqueta visível no painel e na auditoria.
    origem_envio: Mapped[str | None] = mapped_column(String(20))
    origem_envio_obs: Mapped[str | None] = mapped_column(String(120))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revisado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario_rh.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
