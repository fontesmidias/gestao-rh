"""Gravação e transcrição de entrevista (v2.97).

Tabela PRÓPRIA, não colunas na `entrevista` — ver o docstring do modelo. O
resumo: o áudio tem ciclo de vida e retenção próprios (some antes da
entrevista), e ficar fora das fontes que o `services/dossie.py` varre é o que
impede a transcrição de entrar no dossiê que circula (§ 15.4, v2.67).

Revision ID: b8e2d4f6a1c3
Revises: d4a8c2e6b1f3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "b8e2d4f6a1c3"
down_revision = "d4a8c2e6b1f3"
branch_labels = None
depends_on = None

VALORES = ("nao_perguntado", "consentido", "recusado", "aguardando",
           "processando", "pronta", "falhou", "audio_inaudivel")


def upgrade() -> None:
    # `.create(checkfirst=True)` + `create_type=False` no dialeto POSTGRESQL:
    # o `sa.Enum` genérico não respeita a flag e o `create_table` dispararia um
    # segundo CREATE TYPE via evento DDL, dando DuplicateObject (v1.98).
    enum = postgresql.ENUM(*VALORES, name="status_gravacao", create_type=False)
    enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "gravacao_entrevista",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # `unique`: uma gravação por entrevista — duas transcrições da mesma
        # conversa seriam duas versões do que foi dito.
        sa.Column("entrevista_id", UUID(as_uuid=True),
                  sa.ForeignKey("entrevista.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", enum, nullable=False,
                  server_default="nao_perguntado"),
        sa.Column("consentimento_em", sa.DateTime(timezone=True)),
        sa.Column("consentimento_por", sa.String(200)),
        sa.Column("audio_key", sa.String(300)),
        sa.Column("audio_bytes", sa.Integer()),
        sa.Column("audio_tipo", sa.String(100)),
        sa.Column("duracao_s", sa.Integer()),
        sa.Column("gravado_em", sa.DateTime(timezone=True)),
        # `Text` e não `String(n)`: 40 min de fala dão ~6.000 palavras, e
        # dimensionar pelo caminho mais estreito é o defeito da v2.89.1.
        sa.Column("texto", sa.Text()),
        sa.Column("idioma", sa.String(10)),
        sa.Column("modelo", sa.String(60)),
        sa.Column("transcrito_em", sa.DateTime(timezone=True)),
        sa.Column("processamento_s", sa.Integer()),
        sa.Column("erro", sa.String(400)),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_gravacao_entrevista_entrevista_id",
                    "gravacao_entrevista", ["entrevista_id"])
    op.create_index("ix_gravacao_entrevista_status",
                    "gravacao_entrevista", ["status"])


def downgrade() -> None:
    op.drop_index("ix_gravacao_entrevista_status", table_name="gravacao_entrevista")
    op.drop_index("ix_gravacao_entrevista_entrevista_id",
                  table_name="gravacao_entrevista")
    op.drop_table("gravacao_entrevista")
    postgresql.ENUM(name="status_gravacao").drop(op.get_bind(), checkfirst=True)
