"""Papéis do painel (v2.86).

O papel é uma LINHA no banco, não um valor de enum, por uma razão prática: o
Bruno pediu para poder criar papéis próprios pelo front ("os da empresa que não
são do RH", e o que mais aparecer). Enum exigiria migration a cada papel novo —
e, pior, `ALTER TYPE ... ADD VALUE` tem a armadilha das duas revisões separadas
que este projeto já documenta.

`permissoes` é JSON e guarda a lista de chaves do catálogo
(`services/permissoes.py`). Guardar aqui a LISTA ESCOLHIDA, e não uma referência
ao padrão de fábrica, é deliberado: quando um módulo novo registra uma permissão
nova, os papéis que o superadmin já ajustou **não mudam sozinhos**. Um papel
"Recepção" que alguém restringiu à mão não pode ganhar acesso ao módulo novo por
efeito colateral de um deploy — permissão que aparece sem ninguém conceder é o
oposto do controle que este modelo existe para dar. Quem sempre recebe o módulo
novo é o superadmin, e ele o recebe porque `pode()` nem consulta lista.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Papel(Base):
    __tablename__ = "papel"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    # A chave é o identificador estável usado no código e no token de sessão;
    # o rótulo é o que aparece na tela e pode ser reescrito à vontade.
    chave: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    rotulo: Mapped[str] = mapped_column(String(100))
    descricao: Mapped[str | None] = mapped_column(String(400), nullable=True)
    permissoes: Mapped[list] = mapped_column(JSONB, default=list)
    # Papel de fábrica não se apaga: a instalação ficaria sem "superadmin" e sem
    # como voltar atrás. O superadmin ainda edita as permissões dos demais.
    de_fabrica: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
