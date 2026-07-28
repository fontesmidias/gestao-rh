"""Persistência do Match de Vagas (v2.00) — corrige o incidente de
2026-07-28, em que NADA era guardado e cada clique em "Ranquear" refazia as
131 análises do zero, estourando a cota da IA (18 analisados na 1ª rodada,
2 na 2ª, 67 segundos depois).

Três entidades:

- `CurriculoTexto` — texto extraído do currículo, UMA VEZ, no upload. O
  currículo não muda depois de enviado, então reler 131 currículos a cada
  clique era desperdício puro. Guardado JÁ MINIMIZADO (sem CPF/RG/telefone/
  e-mail/CEP — ver `curriculo_texto.minimizar`): se um dia alguém der um
  SELECT sem pensar, não há documento pessoal ali dentro.

- `ProcessamentoMatch` — uma execução de ranqueamento (assíncrona, no worker
  RQ). O RH clica, continua usando o sistema, e volta na aba de Resultados
  quando terminou.

- `AnaliseTalento` — o resultado por pessoa, com o MOTIVO de estar onde está.
  Nunca some com ninguém em silêncio (mesma regra do lote de documento
  crítico em desenvolvimento.py e da importação em massa do Tirvu).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusProcessamento(str, enum.Enum):
    na_fila = "na_fila"
    processando = "processando"
    concluido = "concluido"
    # Concluído mas SEM análise de IA (todos os provedores fora/sem cota):
    # entrega o ranking só com filtro estruturado, dizendo isso — decisão do
    # Bruno: algo útil na mão é melhor que nada.
    concluido_sem_ia = "concluido_sem_ia"
    falhou = "falhou"


class ResultadoAnalise(str, enum.Enum):
    """POR QUE esta pessoa está onde está — o log antigo dizia
    'analisados: 2' e sumia com os outros 129."""
    analisado = "analisado"
    sem_curriculo = "sem_curriculo"
    curriculo_ilegivel = "curriculo_ilegivel"
    ia_indisponivel = "ia_indisponivel"     # não deu para analisar; tentar depois
    erro = "erro"


class CurriculoTexto(Base):
    """Texto do currículo extraído uma vez (OCR/leitura) e reaproveitado em
    todos os ranqueamentos futuros. 1:1 com o talento."""

    __tablename__ = "curriculo_texto"

    talento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), primary_key=True)
    # JÁ MINIMIZADO (sem CPF/RG/telefone/e-mail/CEP)
    texto: Mapped[str | None] = mapped_column(Text)
    # Chave do arquivo lido — se o talento trocar o currículo, a key muda e
    # sabemos que precisa reextrair.
    curriculo_key: Mapped[str | None] = mapped_column(String(300))
    legivel: Mapped[bool] = mapped_column(Boolean, default=False)
    # Motivo curto quando não deu para ler (formato, OCR indisponível…) — o
    # RH precisa saber que `.heic` tem conserto e PDF escaneado precisa de OCR.
    motivo_falha: Mapped[str | None] = mapped_column(String(120))
    caracteres: Mapped[int | None] = mapped_column(Integer)
    extraido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now())


class ProcessamentoMatch(Base):
    """Uma execução de ranqueamento de uma vaga."""

    __tablename__ = "match_processamento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vaga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaga.id", ondelete="CASCADE"), index=True)
    status: Mapped[StatusProcessamento] = mapped_column(
        Enum(StatusProcessamento, name="match_status_processamento"),
        default=StatusProcessamento.na_fila, index=True)
    total_talentos: Mapped[int] = mapped_column(Integer, default=0)
    processados: Mapped[int] = mapped_column(Integer, default=0)  # progresso na aba
    analisados_ia: Mapped[int] = mapped_column(Integer, default=0)
    reaproveitados: Mapped[int] = mapped_column(Integer, default=0)  # análise que já existia
    sem_curriculo: Mapped[int] = mapped_column(Integer, default=0)
    ilegiveis: Mapped[int] = mapped_column(Integer, default=0)
    suspeitos: Mapped[int] = mapped_column(Integer, default=0)   # anti-prompt-injection
    # Mensagem honesta para a tela (ex.: "limite de uso da IA atingido") — o
    # RH clicou de novo em 67s porque a mensagem antiga dizia só "IA
    # indisponível", que ele leu como "caiu, vou tentar de novo".
    observacao: Mapped[str | None] = mapped_column(String(300))
    solicitado_por: Mapped[str | None] = mapped_column(String(200))  # e-mail do RH (snapshot)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnaliseTalento(Base):
    """Resultado por pessoa. Fica amarrado à VAGA (não ao processamento) para
    ser reaproveitado no próximo ranqueamento da mesma vaga — decisão do
    Bruno: clicar de novo tem que ser praticamente grátis."""

    __tablename__ = "match_analise"
    __table_args__ = (
        UniqueConstraint("vaga_id", "talento_id", name="uq_analise_vaga_talento"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vaga_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vaga.id", ondelete="CASCADE"), index=True)
    talento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), index=True)
    # Qual processamento gerou esta análise (rastro; a análise sobrevive a ele)
    processamento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("match_processamento.id", ondelete="SET NULL"), nullable=True)

    resultado: Mapped[ResultadoAnalise] = mapped_column(
        Enum(ResultadoAnalise, name="match_resultado_analise"), index=True)
    nota: Mapped[int | None] = mapped_column(Integer)
    atende_obrigatorios: Mapped[bool | None] = mapped_column(Boolean)
    justificativa: Mapped[str | None] = mapped_column(Text)
    # Filtro estruturado (cargo/região) — calculado local, sem custo de IA
    bate_filtro: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tentativa de manipular a nota detectada no currículo (v1.99) — SEMPRE
    # reportado ao RH, nunca filtrado em silêncio
    curriculo_suspeito: Mapped[bool] = mapped_column(Boolean, default=False)
    provedor: Mapped[str | None] = mapped_column(String(30))  # openrouter | groq
    detalhe_falha: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
