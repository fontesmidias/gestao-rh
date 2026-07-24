"""Mini-CRM do RH: anotações e tags que acompanham a PESSOA por todo o ciclo
de vida (talento → candidato → efetivo → desligado).

A pessoa vive em DOIS registros: `talento` (antes de haver vaga) e `candidato`
(após a conversão; candidato e colaborador são o MESMO registro). O talento NÃO
é apagado ao converter — vira histórico com `talento.candidato_id` apontando
para o candidato criado.

Por isso anotações e vínculos de tag têm DUAS FKs opcionais (`talento_id` e
`candidato_id`), exatamente uma preenchida por registro. A anotação criada no
talento "segue a pessoa" sem cópia: quando o talento já foi convertido, o
detalhe do candidato junta as anotações de ambos os lados (OR na consulta, via
`services/crm.py`). Nada é movido no `converter` — o elo já existe na FK.

Autor: guardamos `autor_id` (FK UsuarioRH) E `autor_nome` (SNAPSHOT) — o nome
não pode sumir da tela se o usuário for removido depois. Registrar "quem lançou,
data e horário" foi pedido explícito (comunicação interna do RH)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Tag(Base):
    """Catálogo de tags do RH (CRUD): "Já entrevistado", "Currículo lido",
    "Serve p/ outra vaga" etc. Catálogo evita "entrevistado"/"Entrevistado"
    virarem tags diferentes. Cor para leitura rápida no dash."""

    __tablename__ = "crm_tag"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    cor: Mapped[str | None] = mapped_column(String(9))   # #RRGGBB (opcional)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PessoaTag(Base):
    """Vínculo N:N tag ↔ pessoa (talento OU candidato). Uma das duas FKs
    preenchida. Marca quem aplicou e quando (auditoria leve)."""

    __tablename__ = "crm_pessoa_tag"
    __table_args__ = (
        UniqueConstraint("tag_id", "talento_id", name="uq_tag_talento"),
        UniqueConstraint("tag_id", "candidato_id", name="uq_tag_candidato"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crm_tag.id", ondelete="CASCADE"), index=True)
    talento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), nullable=True, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True, index=True)
    aplicado_por: Mapped[str | None] = mapped_column(String(200))   # e-mail do RH
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Anotacao(Base):
    """Nota de texto livre sobre a pessoa, com autor+data e anexo opcional.
    Visível a todo o RH (comunicação interna), em qualquer etapa do ciclo."""

    __tablename__ = "crm_anotacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    talento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), nullable=True, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True, index=True)
    texto: Mapped[str] = mapped_column(Text)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_rh.id"), nullable=True)
    autor_nome: Mapped[str] = mapped_column(String(200))   # SNAPSHOT (não some)
    # anexo opcional no MinIO (prefixo crm/anotacoes/{id}/...)
    anexo_key: Mapped[str | None] = mapped_column(String(300))
    anexo_nome: Mapped[str | None] = mapped_column(String(200))
    anexo_tipo: Mapped[str | None] = mapped_column(String(100))   # content-type
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
