"""Links de testagem: aplicação avulsa dos testes (DISC + situacional) fora da
admissão — para o RH validar o instrumento ou aplicar em quem já é da casa.

Diferenças em relação ao teste do candidato: o participante informa SÓ o nome
(sem CPF/e-mail/2FA) e VÊ o próprio resultado ao final — é um ambiente de
testagem, não de seleção. A pontuação continua 100%% no servidor (o gabarito
nunca vai ao frontend)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.teste import StatusTeste, TipoTeste


class LinkTestagem(Base):
    __tablename__ = "link_testagem"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120))
    # token em claro: o RH precisa recopiar a URL depois; o link só dá acesso à
    # testagem anônima (nenhum dado pessoal por trás dele)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_por: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParticipanteTestagem(Base):
    __tablename__ = "participante_testagem"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("link_testagem.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TesteTestagem(Base):
    """Mesmo ciclo do TesteCandidato (pendente → em andamento → concluído/
    expirado), mas ligado a um participante anônimo da testagem."""

    __tablename__ = "teste_testagem"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participante_testagem.id"), index=True)
    tipo: Mapped[TipoTeste] = mapped_column(Enum(TipoTeste, name="tipo_teste"))
    status: Mapped[StatusTeste] = mapped_column(
        Enum(StatusTeste, name="status_teste"), default=StatusTeste.pendente)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prazo_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respostas: Mapped[list] = mapped_column(JSON, default=list)
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
