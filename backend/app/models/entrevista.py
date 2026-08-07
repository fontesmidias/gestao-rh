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

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
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

    # --- Cargo e posto SEM vaga cadastrada (v2.74, pedido do Bruno).
    # Nem toda entrevista nasce de uma vaga aberta: o RH conversa para um posto
    # que precisa repor gente, e cadastrar uma vaga só para marcar a conversa
    # seria burocracia inventada. São ALTERNATIVA ao `vaga_id`, não substituto —
    # havendo vaga, ela continua mandando (e o cargo dela alimenta o roteiro).
    #
    # `cargo` é STRING, não FK: é assim em todo o sistema (`Candidato.cargo_funcao`,
    # `ModeloDocumento.cargo_alvo`, as provas por cargo) e virar tabela quebraria
    # os três. É também o que `resolver_roteiro` casa por `normalizar_cargo`.
    cargo: Mapped[str | None] = mapped_column(String(120))
    # Posto é FK **com snapshot do nome**, mesma razão do `vaga_titulo`: o posto
    # pode ser excluído (vai para a lixeira) e a entrevista tem que continuar
    # legível — dizer para qual posto a conversa foi é metade do registro.
    posto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("posto_servico.id", ondelete="SET NULL"), nullable=True, index=True)
    posto_nome: Mapped[str | None] = mapped_column(String(200))

    tipo: Mapped[TipoEntrevista] = mapped_column(
        String(20), default=TipoEntrevista.entrevista)
    status: Mapped[StatusEntrevista] = mapped_column(
        String(20), default=StatusEntrevista.marcada, index=True)

    # --- Agenda. `marcada_para = None` significa "nasceu já realizada":
    # exigir agendamento prévio mataria o módulo (cenário 3). ---
    marcada_para: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    realizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local: Mapped[str | None] = mapped_column(String(120))

    # --- Modalidade (v2.66, § 14.4). É ela que decide o resto: presencial usa
    # `local` (endereço), online usa `link_reuniao` (URL colada pelo RH — não há
    # integração com a API do Teams, e integrar exigiria app no tenant e OAuth
    # próprio, pelo mesmo raciocínio do `wa.me` do Minutário).
    #
    # **Online sem link não se marca** (cenário 29): o e-mail sairia dizendo
    # "entrevista online" sem dizer por onde, e a pessoa não teria como entrar.
    modalidade: Mapped[str | None] = mapped_column(String(20))    # presencial | online
    link_reuniao: Mapped[str | None] = mapped_column(String(500))

    # --- Convite de calendário (§ 14.4). `SEQUENCE` do RFC 5545: o cliente de
    # agenda só ACEITA a atualização se o número for maior que o que ele já tem
    # — com o mesmo UID e sequência igual, a remarcação é ignorada em silêncio e
    # a pessoa vem no horário velho. Incrementa a cada convite reenviado.
    sequencia_convite: Mapped[int] = mapped_column(Integer, default=0)
    convite_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Carimbo do lembrete da véspera: o worker roda a cada 24h e não pode mandar
    # o mesmo lembrete duas vezes (a pessoa aprende a ignorar — mesma razão do
    # anti-spam do `avisar_vencimentos`).
    lembrete_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- O ROTEIRO com que a avaliação foi feita (v2.66, § 14.1).
    #
    # FK **e** snapshot, pelo mesmo motivo de `vaga_titulo`: o roteiro pode
    # ganhar versão nova ou ser arquivado, e a entrevista tem que continuar
    # legível com as perguntas e âncoras de quando a nota foi dada. Ler do
    # roteiro vivo mostraria o texto de HOJE numa avaliação de meses atrás
    # (cenários 21 e 24) — e a nota deixaria de significar o que significava.
    roteiro_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("roteiro_entrevista.id", ondelete="SET NULL"), nullable=True)
    roteiro_snapshot: Mapped[dict | None] = mapped_column(JSONB)

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

    # --- Duração do compromisso (v2.67, § 15.5 item 4) ---
    #
    # Era a constante `DURACAO_MIN` de `entrevista_convite.py`; virou campo a
    # pedido do Bruno. Alimenta o `DTEND` do `.ics`.
    #
    # **Zero ou negativo é RECUSADO na entrada** (cenário 37): o `DTEND` sairia
    # anterior ao `DTSTART`, e um VEVENT com fim antes do começo é descartado
    # por cliente rígido e desenhado como faixa vazia pelos tolerantes — em
    # ambos os casos a pessoa não vê a entrevista na agenda. O `gerar_ics` tem
    # `max(1, ...)` como rede, mas a rede não pode ser a única defesa: ela
    # silenciaria a duração errada em vez de dizer ao RH que ele digitou 0.
    duracao_min: Mapped[int] = mapped_column(Integer, default=60)

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
