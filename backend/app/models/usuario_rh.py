import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UsuarioRH(Base):
    __tablename__ = "usuario_rh"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(300))
    ativo: Mapped[bool] = mapped_column(default=True)
    # Chave do `Papel` (v2.86). String, não FK: o papel é resolvido pela chave
    # estável, e um papel removido não pode arrastar o usuário junto nem deixar
    # a coluna nula em silêncio — sem papel resolvido, `permissoes_do_usuario`
    # devolve conjunto VAZIO, que nega em vez de liberar.
    papel: Mapped[str] = mapped_column(String(50), default="rh", server_default="rh")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
