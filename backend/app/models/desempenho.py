"""Gestão de Desempenho (Onda C).

Começa pelos **Fatos Observados**, e a ordem é deliberada: eles rodam sozinhos
por um período ANTES do formulário existir, alimentando o banco de fatos.

O porquê (diagnóstico do próprio Bruno, sem usar o termo): *"muitas das vezes o
líder, na hora de avaliar, esquece de algo que o colaborador fez"* — é o efeito
de recência. E a cartilha (pág. 3) exige **fato observável** em vez de rótulo:
"faltou 3 vezes sem aviso em maio", não "tem má vontade". Sem banco de fatos, o
líder abre o formulário com a memória vazia e escreve rótulo, porque rótulo é o
que sobra quando o fato foi esquecido.

Com 6 formulários por avaliador por ciclo, isso seria preenchido às pressas na
véspera — e essas notas decidem efetivação e desligamento.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, ForeignKey,
                        Integer, String, Text, func)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class TipoFato(str, enum.Enum):
    positivo = "positivo"
    negativo = "negativo"
    neutro = "neutro"      # registro de contexto (mudança de posto, atestado…)


class FatoObservado(Base):
    """Algo que a liderança viu e registrou NA HORA, para lembrar na avaliação.

    **O colaborador vê o que foi registrado sobre ele** (regra da Onda C): sem
    isso, não é gestão de desempenho — é dossiê secreto com interface bonita. A
    visibilidade é o que muda o comportamento de quem registra.

    `visivel_em` permite um atraso curto (o líder registra hoje, a pessoa vê na
    conversa de feedback) sem criar registro invisível para sempre.
    """

    __tablename__ = "fato_observado"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id"), index=True)
    # quem registrou (e-mail do RH/liderança) — auditoria e responsabilidade
    autor: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[TipoFato] = mapped_column(
        Enum(TipoFato, name="tipo_fato_observado"), default=TipoFato.positivo,
        index=True)
    # O QUE aconteceu — a cartilha manda descrever fato, não rótulo
    descricao: Mapped[str] = mapped_column(Text)
    # QUAL foi o impacto (no cliente, na equipe, no serviço) — é o que separa
    # "chegou atrasado" de "chegou atrasado e o posto ficou descoberto"
    impacto: Mapped[str | None] = mapped_column(Text)
    ocorrido_em: Mapped[date] = mapped_column(Date, index=True)
    # anexo opcional (foto, vídeo, documento) no MinIO
    anexo_key: Mapped[str | None] = mapped_column(String(300))
    anexo_nome: Mapped[str | None] = mapped_column(String(200))
    anexo_tipo: Mapped[str | None] = mapped_column(String(100))
    anexo_tamanho: Mapped[int | None] = mapped_column(Integer)
    # a partir de quando o colaborador enxerga (None = imediatamente)
    visivel_em: Mapped[date | None] = mapped_column(Date)
    # quando o fato já foi usado numa avaliação, fica o vínculo
    avaliacao_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("avaliacao.id"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now(), index=True)


class OcasiaoAvaliacao(str, enum.Enum):
    """Seção 1 da cartilha — a ocasião é um CAMPO, não um módulo à parte."""
    experiencia_30 = "experiencia_30"
    experiencia_45 = "experiencia_45"
    experiencia_60 = "experiencia_60"
    experiencia_90 = "experiencia_90"
    intermitente = "intermitente"
    periodica = "periodica"
    feedback_pontual = "feedback_pontual"
    outro = "outro"


class RelacaoAvaliador(str, enum.Enum):
    """Quem avalia quem. Governa o ANONIMATO (decisão do Bruno):
    - vertical é IDENTIFICADO (é o líder; a pessoa senta na frente dele);
    - horizontal é ANÔNIMO e AGREGADO (é o colega; identificado, ele mente).
    """
    vertical = "vertical"        # liderança imediata ou de outra área
    horizontal = "horizontal"    # par de mesmo nível
    autoavaliacao = "autoavaliacao"


class StatusAvaliacao(str, enum.Enum):
    """Máquina de estados. A conversa é o produto; o formulário é o registro
    dela — por isso não existe caminho de "preenchida" direto para
    "homologada": o feedback presencial (cartilha, pág. 5) é obrigatório."""
    rascunho = "rascunho"
    preenchida = "preenchida"
    feedback_dado = "feedback_dado"        # conversa aconteceu (com data)
    manifestada = "manifestada"            # o colaborador registrou a seção 9
    homologada = "homologada"              # RH fechou
    cancelada = "cancelada"


class CicloAvaliacao(Base):
    """Janela em que um grupo é avaliado. 4 por ano (decisão do Bruno), com
    datas configuráveis pelo front — geral, por posto ou individual."""

    __tablename__ = "ciclo_avaliacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120))          # "3º trimestre 2026"
    inicio_em: Mapped[date] = mapped_column(Date)
    fim_em: Mapped[date] = mapped_column(Date)
    # escopo: vazio = todo mundo; senão restringe a postos/pessoas
    postos: Mapped[list | None] = mapped_column(JSON)
    candidatos: Mapped[list | None] = mapped_column(JSON)
    encerrado: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())


class Avaliacao(Base):
    """Uma avaliação de UMA pessoa por UM avaliador — as 11 seções da cartilha
    `docs/Cartilha do Avaliador e Formulário, de 17-06-2026.pdf`.

    O instrumento NÃO foi inventado aqui: ele já rodava no Microsoft Forms. As
    escalas, as 8 competências e as 5 recomendações vêm de lá, palavra por
    palavra.
    """

    __tablename__ = "avaliacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    ciclo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ciclo_avaliacao.id"), index=True)
    candidato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidato.id"), index=True)          # o avaliado
    avaliador: Mapped[str] = mapped_column(String(200), index=True)  # e-mail
    relacao: Mapped[RelacaoAvaliador] = mapped_column(
        Enum(RelacaoAvaliador, name="relacao_avaliador"),
        default=RelacaoAvaliador.vertical)
    ocasiao: Mapped[OcasiaoAvaliacao] = mapped_column(
        Enum(OcasiaoAvaliacao, name="ocasiao_avaliacao"),
        default=OcasiaoAvaliacao.periodica)
    status: Mapped[StatusAvaliacao] = mapped_column(
        Enum(StatusAvaliacao, name="status_avaliacao"),
        default=StatusAvaliacao.rascunho, index=True)

    # seção 1 — período avaliado
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    convocacao_em: Mapped[date | None] = mapped_column(Date)   # intermitente
    ocasiao_outro: Mapped[str | None] = mapped_column(String(120))

    # seções 2 e 3 — {chave_do_item: valor_da_escala}
    indicadores: Mapped[dict | None] = mapped_column(JSON)
    competencias: Mapped[dict | None] = mapped_column(JSON)

    # seções 4 e 5 — texto livre
    pontos_fortes: Mapped[str | None] = mapped_column(Text)
    pontos_desenvolver: Mapped[str | None] = mapped_column(Text)

    # seção 6 — PDI: [{o_que, acao, prazo, acompanhar_em}]
    pdi: Mapped[list | None] = mapped_column(JSON)

    # seção 7 — recomendação + justificativa
    recomendacao: Mapped[str | None] = mapped_column(String(40))
    recomendacao_data: Mapped[date | None] = mapped_column(Date)  # prorrogar/reavaliar até
    justificativa: Mapped[str | None] = mapped_column(Text)

    # seção 8 — postura ao receber o feedback (preenchida pelo gestor)
    postura: Mapped[str | None] = mapped_column(String(20))  # receptivo|neutro|resistente
    postura_observacao: Mapped[str | None] = mapped_column(Text)
    feedback_em: Mapped[date | None] = mapped_column(Date)   # data da CONVERSA

    # seção 9 — manifestação do COLABORADOR (direito de resposta)
    manifestacao: Mapped[str | None] = mapped_column(Text)
    manifestacao_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # seção 10 — conclusão do aplicador (RH)
    conclusao_aplicador: Mapped[str | None] = mapped_column(Text)

    # homologação (seção 11 é a assinatura; o RH homologa)
    homologado_por: Mapped[str | None] = mapped_column(String(200))
    homologado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now(), index=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ciclo: Mapped["CicloAvaliacao | None"] = relationship()
