"""Provas por cargo: banco de provas CONFIGURÁVEL pelo RH (diferente do DISC/
situacional, que têm gabarito fixo no código). O RH monta as questões — objetivas
(múltipla escolha, corrigidas automaticamente) e discursivas (texto aberto,
corrigidas à mão) — e aplica por link avulso, como a testagem (/t/).

Segurança: o GABARITO das objetivas fica SÓ no servidor (nunca vai ao público),
igual ao DISC. O participante NÃO vê a própria nota — é seleção, restrita ao RH.
"""

import uuid
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProvaCargo(Base):
    """O modelo/template de uma prova (editável pelo RH), opcionalmente por cargo."""

    __tablename__ = "prova_cargo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    titulo: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str | None] = mapped_column(String(120), index=True)  # None = genérica
    descricao: Mapped[str | None] = mapped_column(Text)
    tempo_segundos: Mapped[int] = mapped_column(Integer, default=1800)  # timer (30 min padrão)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Aleatorização: embaralha ordem de questões E alternativas por participante
    # (seed estável por aplicação — recarregar não reembaralha). Interruptor por
    # prova: prova didática com sequência proposital fica com False.
    embaralhar: Mapped[bool] = mapped_column(Boolean, default=False)
    # Ao concluir, o participante vê o gabarito + explicação de cada questão?
    # Seleção: False (não vaza gabarito). Treinamento/didática: True.
    mostrar_explicacao: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_por: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now())

    questoes: Mapped[list["QuestaoProva"]] = relationship(
        back_populates="prova", cascade="all, delete-orphan")


class QuestaoProva(Base):
    """Uma questão de uma prova. Objetiva: `opcoes` (lista de {id, texto}) +
    `gabarito` (id da opção correta — NUNCA sai ao público). Discursiva: só
    enunciado; a resposta é texto livre corrigido pelo RH."""

    __tablename__ = "questao_prova"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prova_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prova_cargo.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    enunciado: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(12))  # 'objetiva' | 'discursiva'
    opcoes: Mapped[list | None] = mapped_column(JSON)     # [{id, texto}] (objetiva)
    gabarito: Mapped[str | None] = mapped_column(String(40))  # id da opção certa (objetiva)
    # Explicação opcional da resposta (por que a correta é correta). Só vai ao
    # participante se ProvaCargo.mostrar_explicacao — nunca vaza na aplicação.
    explicacao: Mapped[str | None] = mapped_column(Text)
    peso: Mapped[int] = mapped_column(Integer, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prova: Mapped[ProvaCargo] = relationship(back_populates="questoes")


class LinkProva(Base):
    """Link avulso que aplica uma prova (espelha LinkTestagem). Token em claro —
    o RH recopia a URL. Pode ser enviado a um talento (talento_id)."""

    __tablename__ = "link_prova"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prova_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prova_cargo.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))   # rótulo do link (ex.: nome da prova/pessoa)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    talento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("talento.id"), nullable=True, index=True)
    email_destino: Mapped[str | None] = mapped_column(String(200))
    criado_por: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AplicacaoProva(Base):
    """Uma pessoa respondendo a prova por um link. Guarda respostas cruas,
    telemetria, e as notas (objetivas automáticas + discursivas do RH)."""

    __tablename__ = "aplicacao_prova"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    link_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("link_prova.id"), index=True)
    prova_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prova_cargo.id"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(14), default="pendente")
    # pendente | em_andamento | concluido | expirado
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prazo_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Semente do embaralhamento: gerada no início, torna a ordem de questões e
    # alternativas ESTÁVEL para este participante (mesma seed → mesma ordem). A
    # correção casa por id, então embaralhar a exibição não afeta a nota.
    seed: Mapped[int | None] = mapped_column(Integer)
    respostas: Mapped[list] = mapped_column(JSON, default=list)  # [{questao_id, escolha|texto}]
    eventos: Mapped[list] = mapped_column(JSON, default=list)    # telemetria
    # notas (0-100). objetivas: automática; discursivas: do RH; final: combinada.
    nota_objetivas: Mapped[float | None] = mapped_column(Float)
    nota_discursivas: Mapped[float | None] = mapped_column(Float)
    nota_final: Mapped[float | None] = mapped_column(Float)
    correcao_discursivas: Mapped[dict | None] = mapped_column(JSON)  # {qid: {nota, comentario}}
    corrigido_por: Mapped[str | None] = mapped_column(String(200))
    corrigido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
