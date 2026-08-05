"""Entrevista (v2.64): o degrau que faltava entre "o RH olhou o currículo" e
"o RH mandou o convite".

Duas naturezas na MESMA tabela, distinguidas por `tipo`:

- **triagem** — checagem de viabilidade por telefone. SEM nota, SEM competência,
  SEM âncora. Perguntas de sim/não que decidem se vale gastar uma hora
  presencial. É outra coisa, não uma entrevista curta.
- **entrevista** — avaliação ancorada: 4 competências, escala 1–4, justificativa
  obrigatória em cada uma.

**A pessoa vive em DOIS registros** (`talento` e `candidato`, ligados por
`talento.candidato_id`). Por isso há DUAS FKs opcionais, exatamente uma
preenchida — é o padrão do mini-CRM (`models/crm.py`). Com FK única, a
entrevista feita com o talento SUMIRIA da ficha depois do `converter()`, que é
justamente o momento em que ela mais importa (cenário 6).

**`vaga_id` é nullable com `ondelete=SET NULL` + snapshot `vaga_titulo`**:
`DELETE /rh/vagas/{id}` (`vagas.py:111`) é delete FÍSICO e não passa pela
lixeira. Sem o SET NULL a entrevista iria junto; sem o snapshot ela sobreviveria
anônima, dizendo "vaga excluída" onde deveria dizer o nome (cenário 4).

O instrumento (competências, âncoras, escalas, perguntas) **não mora aqui nem
no banco** — vive em `services/entrevistas.py` como constante de módulo, pelo
mesmo motivo que a cartilha de desempenho não está no banco: o front lê da API
e não duplica texto.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TipoEntrevista(str, Enum):
    triagem = "triagem"          # checagem de viabilidade (telefone)
    entrevista = "entrevista"    # avaliação ancorada (presencial/vídeo)


class StatusEntrevista(str, Enum):
    marcada = "marcada"          # data futura, nada preenchido
    realizada = "realizada"      # aconteceu e foi preenchida
    nao_veio = "nao_veio"        # não compareceu — SEMPRE marcado por gente
    remarcada = "remarcada"      # terminal; gera uma nova linha
    cancelada = "cancelada"
    arquivada = "arquivada"      # 180 dias — sai da vista, NÃO some


# Status que já tiveram desfecho — não entram na fila de pendências.
STATUS_TERMINAIS = {
    StatusEntrevista.realizada, StatusEntrevista.nao_veio,
    StatusEntrevista.remarcada, StatusEntrevista.cancelada,
    StatusEntrevista.arquivada,
}


class Entrevista(Base):
    __tablename__ = "entrevista"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # --- A pessoa: padrão do mini-CRM, exatamente uma preenchida ---
    talento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("talento.id", ondelete="CASCADE"), nullable=True, index=True)
    candidato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True, index=True)

    # --- O vínculo com a vaga. NULLABLE de propósito: entrevista exploratória
    # sem vaga é cenário real (cenário 5). ---
    vaga_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vaga.id", ondelete="SET NULL"), nullable=True, index=True)
    # Snapshot: a vaga pode ser excluída fisicamente (cenário 4).
    vaga_titulo: Mapped[str | None] = mapped_column(String(160))

    tipo: Mapped[TipoEntrevista] = mapped_column(
        String(20), default=TipoEntrevista.entrevista)
    status: Mapped[StatusEntrevista] = mapped_column(
        String(20), default=StatusEntrevista.marcada, index=True)

    # --- Agenda. `marcada_para = None` significa "nasceu já realizada":
    # exigir agendamento prévio mataria o módulo (cenário 3). ---
    marcada_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    realizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local: Mapped[str | None] = mapped_column(String(120))

    # --- Quem conduziu: FK + SNAPSHOT (o nome não some se o usuário for
    # removido) — padrão do mini-CRM e do Desempenho. ---
    entrevistador_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario_rh.id"), nullable=True)
    entrevistador_nome: Mapped[str] = mapped_column(String(200))

    # --- TRIAGEM (tipo == triagem) ---
    # {aceita_escala, aceita_salario, consegue_chegar, tem_interesse,
    #  recebe_seguro_desemprego} -> "sim" | "nao" | "nao_sei"
    triagem: Mapped[dict | None] = mapped_column(JSONB)
    triagem_desfecho: Mapped[str | None] = mapped_column(String(20))

    # --- ENTREVISTA (tipo == entrevista) ---
    # Mesmo padrão de Avaliacao.competencias: dict JSON, sem tabela por item.
    competencias: Mapped[dict | None] = mapped_column(JSONB)      # {chave: 1..4}
    justificativas: Mapped[dict | None] = mapped_column(JSONB)    # {chave: "texto"}
    variante: Mapped[str | None] = mapped_column(String(20))      # comportamental | situacional
    recomendacao: Mapped[str | None] = mapped_column(String(30))
    recomendacao_motivo: Mapped[str | None] = mapped_column(Text)

    observacao: Mapped[str | None] = mapped_column(Text)

    # --- Anexo (padrão api/crm.py:160) ---
    anexo_key: Mapped[str | None] = mapped_column(String(300))
    anexo_nome: Mapped[str | None] = mapped_column(String(200))
    anexo_tipo: Mapped[str | None] = mapped_column(String(100))

    # Defasagem de preenchimento: memória decai rápido, quem preenche no dia
    # seguinte RECONSTRÓI. Não se proíbe (proibir faz o RH não registrar) — se
    # carimba a distância entre `realizada_em` e `preenchida_em` na tela.
    preenchida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    criada_por: Mapped[str | None] = mapped_column(String(200))
    arquivada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
