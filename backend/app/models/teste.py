"""Testes do candidato (inventário DISC e teste situacional).

Criados no convite quando o RH marca as caixinhas. O candidato se identifica
minimamente (nome/CPF/e-mail) com confirmação em duas etapas por código no
e-mail, responde e segue para o cadastro. O RESULTADO é restrito ao RH."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TipoTeste(str, enum.Enum):
    disc = "disc"
    situacional = "situacional"


class StatusTeste(str, enum.Enum):
    pendente = "pendente"          # aguardando o candidato
    em_andamento = "em_andamento"  # iniciou (timer correndo)
    concluido = "concluido"
    expirado = "expirado"          # estourou o tempo sem concluir


class TesteCandidato(Base):
    __tablename__ = "teste_candidato"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidato.id"), index=True)
    tipo: Mapped[TipoTeste] = mapped_column(Enum(TipoTeste, name="tipo_teste"))
    status: Mapped[StatusTeste] = mapped_column(
        Enum(StatusTeste, name="status_teste"), default=StatusTeste.pendente)
    # identificação mínima confirmada antes do teste (2FA por código no e-mail)
    identificado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    codigo_hash: Mapped[str | None] = mapped_column(String(64))
    codigo_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prazo_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # respostas cruas + resultado calculado (só o RH lê o resultado)
    respostas: Mapped[list] = mapped_column(JSON, default=list)
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)
    # telemetria de comportamento durante o teste (saídas de tela, troca de
    # aba/janela, tentativa de print, cópia/cola, queda de conexão) — eventos
    # crus para o RH ler ou mandar para uma IA analisar. Informado ao
    # candidato nas instruções (LGPD: transparência, art. 9º).
    eventos: Mapped[list] = mapped_column(JSON, default=list)
    aceite_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
