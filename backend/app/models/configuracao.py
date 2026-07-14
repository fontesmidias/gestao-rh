from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Configuracao(Base):
    """Configurações editáveis pelo painel (chave/valor). Sobrepõem o .env."""

    __tablename__ = "configuracao"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
