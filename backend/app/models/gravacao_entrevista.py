"""Gravação e transcrição de entrevista (v2.97).

Desenho e decisões em `docs/planejamento/14-transcricao-de-entrevistas.md`.
O essencial, e o porquê de cada escolha estrutural:

**Tabela PRÓPRIA, não colunas na `Entrevista`.** Duas razões. A primeira é o
ciclo de vida: a entrevista dura para sempre (é peça de avaliação), o áudio não
— ele tem retenção própria e some antes dela. A segunda é o § 7 do documento: o
`services/dossie.py` varre `SolicitacaoAssinatura` **sem filtrar origem**, e todo
fluxo novo que encoste nas fontes do dossiê entra nele POR PADRÃO. Uma tabela à
parte, fora daquelas três fontes, é a mesma contenção que a v2.67 usou para a
ficha de entrevista assinada — que não pode circular junto do dossiê de admissão.

**O consentimento é um estado do REGISTRO, não um booleano no candidato.**
Gravação de voz é dado pessoal e há entendimento de que voz é biométrico: a
autorização é para AQUELA entrevista, não para sempre. Um `consentiu=True` no
cadastro da pessoa autorizaria gravações futuras que ninguém pediu.

**`recusado` é um estado, não a ausência de `consentido`.** É a lição do creche
(v2.34): sem manifestação registrada, "não respondeu" e "disse não" são a mesma
linha em branco, e não se prova que a pessoa foi consultada. Aqui é pior — numa
entrevista de emprego, de um lado está quem decide e do outro quem precisa do
emprego; a assimetria exige que a recusa fique registrada como ATO.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StatusGravacao(str, enum.Enum):
    """Estados possíveis, e cada um existe para NÃO deixar silêncio.

    A regra é a do Match (v2.00): *"ninguém some em silêncio"*. Ausência de
    transcrição sem motivo faria o entrevistador achar que o sistema perdeu o
    trabalho dele — e o trabalho é a entrevista inteira.
    """

    # Ninguém foi perguntado ainda. Estado inicial de toda entrevista.
    nao_perguntado = "nao_perguntado"
    # A pessoa autorizou. Só aqui se pode gravar.
    consentido = "consentido"
    # A pessoa disse NÃO — e isso é um registro, não um vazio (ver docstring).
    recusado = "recusado"
    # Áudio no storage, esperando o worker.
    aguardando = "aguardando"
    processando = "processando"
    pronta = "pronta"
    # Falhou, COM motivo legível. Nunca um vazio.
    falhou = "falhou"
    # Gravou, mas não deu para transcrever (áudio mudo, ruído, formato).
    audio_inaudivel = "audio_inaudivel"


class GravacaoEntrevista(Base):
    __tablename__ = "gravacao_entrevista"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    # `unique`: uma gravação por entrevista. Duas transcrições da mesma conversa
    # seriam duas versões do que foi dito, e a ficha aponta para uma só.
    entrevista_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entrevista.id", ondelete="CASCADE"),
        unique=True, index=True)

    status: Mapped[StatusGravacao] = mapped_column(
        Enum(StatusGravacao, name="status_gravacao", create_type=False),
        default=StatusGravacao.nao_perguntado, index=True)

    # --- Consentimento -----------------------------------------------------
    #
    # Quem consentiu é a PESSOA entrevistada; quem REGISTRA é o entrevistador,
    # que estava na sala. Guardar os dois é o que descreve o ato real: o sistema
    # não viu a pessoa dizer sim — viu o entrevistador afirmar que ela disse.
    # É o mesmo princípio do manifesto assistido (v2.56) e do cadastro pelo RH
    # (v2.73): o registro descreve o ato REAL, nunca a versão conveniente.
    consentimento_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consentimento_por: Mapped[str | None] = mapped_column(String(200))  # snapshot

    # --- Áudio -------------------------------------------------------------
    audio_key: Mapped[str | None] = mapped_column(String(300))
    audio_bytes: Mapped[int | None] = mapped_column(Integer)
    audio_tipo: Mapped[str | None] = mapped_column(String(100))
    duracao_s: Mapped[int | None] = mapped_column(Integer)
    gravado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Transcrição -------------------------------------------------------
    #
    # `Text`, não `String(n)`: uma entrevista de 40 min dá ~6.000 palavras, e
    # dimensionar pelo caminho mais estreito é o defeito da v2.89.1.
    texto: Mapped[str | None] = mapped_column(Text)
    idioma: Mapped[str | None] = mapped_column(String(10))
    modelo: Mapped[str | None] = mapped_column(String(60))   # ex.: "small"
    transcrito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Quanto o worker levou. Serve para dimensionar o container quando o volume
    # crescer — sem isso, "está lento" é impressão.
    processamento_s: Mapped[int | None] = mapped_column(Integer)

    # O motivo da falha, em português e legível. Estado sem motivo obriga a
    # abrir o log para saber o que aconteceu — e quem opera não abre log.
    erro: Mapped[str | None] = mapped_column(String(400))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())

    @property
    def pode_gravar(self) -> bool:
        """Só se grava com consentimento registrado. Concentrado numa
        propriedade porque espalhar a regra pelos chamadores faz uma das cópias
        esquecer de conferir — e a que esquece não dá erro, só grava."""
        return self.status == StatusGravacao.consentido
