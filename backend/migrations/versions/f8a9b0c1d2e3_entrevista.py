"""Módulo de Entrevistas — o degrau que faltava no funil (v2.64).

Uma tabela só. O instrumento (competências, âncoras, escalas, perguntas) NÃO
vem para o banco — vive em `services/entrevistas.py` como constante de módulo,
pelo mesmo motivo que a cartilha do avaliador não está aqui: o front lê da API
e não duplica texto. Mudar uma âncora não pode exigir migration.

Três decisões de schema que carregam regra de negócio:

1. **DUAS FKs opcionais de pessoa** (`talento_id`/`candidato_id`), padrão do
   mini-CRM. Com FK única, a entrevista feita com o talento sumiria da ficha
   depois do `converter()` — que é justamente quando ela mais importa.

2. **`vaga_id` com `ondelete=SET NULL` + snapshot `vaga_titulo`**:
   `DELETE /rh/vagas/{id}` é delete FÍSICO e não passa pela lixeira. Sem o SET
   NULL a entrevista iria junto com a vaga; sem o snapshot ela sobreviveria
   anônima. A entrevista sobrevive à vaga, com o nome dela preservado.

3. **`tipo` e `status` são String(20), NÃO enum do Postgres** — de propósito.
   O projeto já pagou caro por enum em migration duas vezes (`DuplicateObject`
   com `sa.Enum` genérico; e a regra das DUAS revisões para adicionar E usar um
   valor novo, que o `transaction_per_migration` impõe). Aqui os valores são
   vocabulário de produto que ainda vai mexer — `String` + Enum do Python no
   modelo dá a mesma garantia na aplicação sem travar o schema.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entrevista",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),

        # A pessoa: exatamente uma preenchida (padrão do mini-CRM).
        sa.Column("talento_id", UUID(as_uuid=True),
                  sa.ForeignKey("talento.id", ondelete="CASCADE"), nullable=True),
        sa.Column("candidato_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True),

        # A vaga sobrevive à exclusão como snapshot.
        sa.Column("vaga_id", UUID(as_uuid=True),
                  sa.ForeignKey("vaga.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vaga_titulo", sa.String(160), nullable=True),

        sa.Column("tipo", sa.String(20), nullable=False, server_default="entrevista"),
        sa.Column("status", sa.String(20), nullable=False, server_default="marcada"),

        # Agenda. marcada_para NULL = nasceu já realizada (cenário 3).
        sa.Column("marcada_para", sa.DateTime(timezone=True), nullable=True),
        sa.Column("realizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local", sa.String(120), nullable=True),

        # Quem conduziu: FK + snapshot do nome.
        sa.Column("entrevistador_id", UUID(as_uuid=True),
                  sa.ForeignKey("usuario_rh.id"), nullable=True),
        sa.Column("entrevistador_nome", sa.String(200), nullable=False),

        # Triagem (sem nota, sem competência, sem âncora).
        sa.Column("triagem", JSONB, nullable=True),
        sa.Column("triagem_desfecho", sa.String(20), nullable=True),

        # Entrevista (avaliação ancorada).
        sa.Column("competencias", JSONB, nullable=True),
        sa.Column("justificativas", JSONB, nullable=True),
        sa.Column("variante", sa.String(20), nullable=True),
        sa.Column("recomendacao", sa.String(30), nullable=True),
        sa.Column("recomendacao_motivo", sa.Text, nullable=True),

        sa.Column("observacao", sa.Text, nullable=True),

        sa.Column("anexo_key", sa.String(300), nullable=True),
        sa.Column("anexo_nome", sa.String(200), nullable=True),
        sa.Column("anexo_tipo", sa.String(100), nullable=True),

        sa.Column("preenchida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criada_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("criada_por", sa.String(200), nullable=True),
        sa.Column("arquivada_em", sa.DateTime(timezone=True), nullable=True),
    )
    # Índices das consultas reais: memória da pessoa (dois lados), comparação
    # por vaga, cards da lista e a varredura de pendências por data.
    op.create_index("ix_entrevista_talento_id", "entrevista", ["talento_id"])
    op.create_index("ix_entrevista_candidato_id", "entrevista", ["candidato_id"])
    op.create_index("ix_entrevista_vaga_id", "entrevista", ["vaga_id"])
    op.create_index("ix_entrevista_status", "entrevista", ["status"])
    op.create_index("ix_entrevista_marcada_para", "entrevista", ["marcada_para"])


def downgrade() -> None:
    op.drop_index("ix_entrevista_marcada_para", table_name="entrevista")
    op.drop_index("ix_entrevista_status", table_name="entrevista")
    op.drop_index("ix_entrevista_vaga_id", table_name="entrevista")
    op.drop_index("ix_entrevista_candidato_id", table_name="entrevista")
    op.drop_index("ix_entrevista_talento_id", table_name="entrevista")
    op.drop_table("entrevista")
