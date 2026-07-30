"""Alertas de telemetria — o sistema avisa em vez de esperar você perguntar (v2.25).

A telemetria da v2.24 grava tudo certo, mas é PASSIVA: alguém precisa abrir a
aba e olhar. No incidente de 2026-07-29 isso não bastaria — o erro estaria
gravado às 11h01 e o Bruno só descobriria quando o candidato ligasse. O dado
existiria; a descoberta continuaria dependendo de reclamação.

As regras são EDITÁVEIS na tela (decisão do Bruno, 2026-07-30): ele pediu para
"customizar mais cenários, conforme o que estiver previsto". Chumbar os quatro
tipos no código obrigaria um deploy a cada limiar novo, e quem convive com os
números é quem deve ajustá-los.

O que NÃO é configurável, e por quê: o dedup e a janela de silêncio. Aviso que
vira ruído deixa de ser lido — e um alerta ignorado é pior que alerta nenhum,
porque dá falsa sensação de cobertura. Cada regra tem `silencio_min`, mas o
sistema NUNCA manda o mesmo alerta duas vezes dentro da janela.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, DateTime, Index, Integer, String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TipoAlerta(str, enum.Enum):
    """Os quatro cenários escolhidos pelo Bruno (2026-07-30).

    Cada um responde a uma pergunta diferente — não são variações do mesmo
    alarme:
    """

    # "Apareceu algo que nunca tinha aparecido." O caso de 2026-07-29.
    erro_novo = "erro_novo"
    # "Um erro CONHECIDO explodiu de volume." Assinatura clássica de deploy ruim.
    erro_volume = "erro_volume"
    # "Muita gente travando no mesmo ponto." Não é desatenção: algo quebrou.
    friccao_pico = "friccao_pico"
    # "Uma página passou do tempo aceitável." MinIO cheio, banco lento.
    lentidao = "lentidao"


class RegraAlerta(Base):
    """Uma regra configurada pelo RH. Várias podem coexistir por tipo."""

    __tablename__ = "regra_alerta"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    tipo: Mapped[TipoAlerta] = mapped_column(String(20), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Limiar: quantas ocorrências disparam. Sem significado para `erro_novo`
    # (que dispara na primeira) e, em `lentidao`, é o tempo em MILISSEGUNDOS.
    limiar: Mapped[int] = mapped_column(Integer, default=1)
    # Janela de observação, em minutos: "N ocorrências EM X minutos".
    janela_min: Mapped[int] = mapped_column(Integer, default=60)
    # Silêncio depois de disparar: impede o mesmo alerta de repetir. É o que
    # separa um aviso útil de uma enxurrada que ninguém lê.
    silencio_min: Mapped[int] = mapped_column(Integer, default=60)

    # Restringe a regra a uma origem (candidato, rh…) ou a uma página. Vazio =
    # vale para tudo. Permite "só me avise de erro do CANDIDATO", que é o que
    # trava contratação.
    origem: Mapped[str | None] = mapped_column(String(20))
    pagina: Mapped[str | None] = mapped_column(String(120))
    # Restringe a um evento específico (ex.: só `documento_reenviado`).
    evento: Mapped[str | None] = mapped_column(String(60))

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())


class AlertaEnviado(Base):
    """Alerta já disparado — memória do dedup e da janela de silêncio.

    Sem esta tabela, o `erro_novo` mandaria e-mail a cada verificação enquanto o
    erro continuasse acontecendo: exatamente o ruído que faria o RH parar de
    ler. É também o que dá sentido a "novo" — novo é o que não está aqui.
    """

    __tablename__ = "alerta_enviado"
    __table_args__ = (
        Index("ix_alerta_assinatura_data", "assinatura", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    regra_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    tipo: Mapped[str] = mapped_column(String(20), index=True)
    # Identidade do que disparou (ex.: tipo + mensagem do erro + página). É a
    # chave do dedup: mesma assinatura dentro do silêncio não avisa de novo.
    assinatura: Mapped[str] = mapped_column(String(300), index=True)
    resumo: Mapped[str | None] = mapped_column(Text)
    ocorrencias: Mapped[int] = mapped_column(Integer, default=0)
    destinatarios: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True)
