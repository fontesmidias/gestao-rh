"""Bloco de áudio de uma gravação de entrevista (v2.98).

**Por que a gravação é dividida em blocos** (decisão do Bruno, 2026-08-12):
uma entrevista real dura 40–90 minutos, e um arquivo único desse tamanho tem
três problemas concretos:

1. **Se o navegador cair aos 32 minutos, perde-se tudo.** Com blocos fechados a
   cada 10 min, o que já subiu está salvo — e a entrevista não se refaz.
2. **O envio de um arquivo de 90 min pode estourar o `proxy_read_timeout` do
   nginx** justamente no fim, depois de a conversa terminar.
3. **A transcrição processa bloco a bloco**, então o RH vê o texto do começo
   enquanto o fim ainda roda, em vez de esperar tudo.

O tamanho do bloco é **configurável no painel** (`transcricao_bloco_min`, padrão
10): sala com internet ruim pede blocos menores; entrevista curta não precisa de
divisão nenhuma.

⚠️ **A ORDEM é o `indice`, nunca a listagem do storage.** A listagem é
lexicográfica e põe `bloco-10` antes de `bloco-2` — a transcrição sairia com o
meio da conversa no lugar errado, e ninguém perceberia lendo (é a armadilha da
v2.35, onde o verso do RG aparecia no lugar da frente).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, Enum, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusBloco(str, enum.Enum):
    aguardando = "aguardando"
    processando = "processando"
    pronta = "pronta"
    falhou = "falhou"
    # Gravou, mas não há fala reconhecível NESTE bloco. Comum e legítimo: o
    # silêncio enquanto a pessoa lê um documento, por exemplo. Não contamina o
    # resto — a gravação só é `audio_inaudivel` se TODOS os blocos forem.
    inaudivel = "inaudivel"


class BlocoGravacao(Base):
    __tablename__ = "bloco_gravacao"
    # Um índice por gravação: reenviar o bloco 3 SUBSTITUI, não duplica.
    __table_args__ = (UniqueConstraint("gravacao_id", "indice",
                                       name="uq_bloco_gravacao_indice"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    gravacao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gravacao_entrevista.id", ondelete="CASCADE"),
        index=True)

    # 1, 2, 3… É esta coluna que ordena — ver o ⚠️ do topo.
    indice: Mapped[int] = mapped_column(Integer)

    audio_key: Mapped[str | None] = mapped_column(String(300))
    audio_bytes: Mapped[int | None] = mapped_column(Integer)
    audio_tipo: Mapped[str | None] = mapped_column(String(100))
    duracao_s: Mapped[int | None] = mapped_column(Integer)
    # Em que segundo da entrevista este bloco começa. É o que permite dizer
    # "[12:30]" no PDF com marcação de tempo, e reouvir no ponto certo.
    inicio_s: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[StatusBloco] = mapped_column(
        Enum(StatusBloco, name="status_bloco_gravacao", create_type=False),
        default=StatusBloco.aguardando, index=True)
    texto: Mapped[str | None] = mapped_column(Text)
    erro: Mapped[str | None] = mapped_column(String(400))
    transcrito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processamento_s: Mapped[int | None] = mapped_column(Integer)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
