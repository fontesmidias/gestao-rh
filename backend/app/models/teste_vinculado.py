"""Teste JÁ RESPONDIDO, aproveitado para um candidato (v2.21).

Pedido do Bruno (2026-07-29): "quero que, ao criar o link para enviar a
documentação, vincular algum teste que a pessoa já fez — seja DISC, seja
situacional, ou seja alguma prova mesmo que eu criei; isso não precisa
aparecer para o candidato, mas sim para o RH".

O caso real: a pessoa respondeu a um teste no Banco de Talentos ou por um link
avulso ANTES de virar candidata. Refazer o mesmo teste na admissão é desperdício
para ela e ruído para o RH — o que valia era o resultado que já existe.

Duas decisões que governam o desenho:

1. **Aponta, não copia.** O vínculo guarda a referência ao teste original
   (participante da testagem, ou aplicação de prova). O resultado continua
   morando onde foi produzido, com a data e o link de origem — se copiássemos,
   teríamos duas versões do mesmo dado e nenhuma delas confiável.

2. **A identidade nem sempre é certa, e isso fica REGISTRADO.** O link avulso
   de testagem é anônimo por desenho: `ParticipanteTestagem` guarda só o nome.
   Quando o teste veio pelo Banco de Talentos (`talento_id`), o sistema sabe de
   quem é — `automatico=True`. Quando o RH escolheu da lista pelo nome, é um
   julgamento humano — `automatico=False`, com autor e data. Homônimo existe, e
   teste decide contratação: quem vier depois precisa saber se aquele vínculo
   foi deduzido pelo sistema ou afirmado por uma pessoa.

O candidato NUNCA vê isto: não entra no wizard, não entra no dossiê (que
circula), só na ficha e na lista do painel.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, Enum, ForeignKey, String, UniqueConstraint,
                        func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class OrigemTesteVinculado(str, enum.Enum):
    """De onde veio o resultado aproveitado."""

    testagem = "testagem"   # DISC/situacional por link avulso (/t/{token})
    prova = "prova"         # prova por cargo criada pelo RH (/p/{token})


class TesteVinculado(Base):
    __tablename__ = "teste_vinculado"
    __table_args__ = (
        # o mesmo teste não entra duas vezes na mesma pessoa
        UniqueConstraint("candidato_id", "participante_id",
                         name="uq_vinculo_participante"),
        UniqueConstraint("candidato_id", "aplicacao_id",
                         name="uq_vinculo_aplicacao"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id", ondelete="CASCADE"), index=True)
    origem: Mapped[OrigemTesteVinculado] = mapped_column(
        Enum(OrigemTesteVinculado, name="origem_teste_vinculado"))

    # Uma das duas é preenchida, conforme a origem — o resultado é lido de lá,
    # nunca copiado para cá.
    participante_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("participante_testagem.id", ondelete="CASCADE"),
        nullable=True, index=True)
    aplicacao_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("aplicacao_prova.id", ondelete="CASCADE"),
        nullable=True, index=True)

    # True = o sistema deduziu (o teste tinha `talento_id` e a pessoa veio do
    # Banco de Talentos). False = o RH escolheu da lista pelo nome, e homônimo
    # é possível. Quem consultar depois precisa saber a diferença.
    automatico: Mapped[bool] = mapped_column(default=False)
    # SNAPSHOT do autor (não FK): remover o usuário do painel não pode apagar
    # quem afirmou que aquele resultado é daquela pessoa.
    vinculado_por: Mapped[str | None] = mapped_column(String(200))
    vinculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
