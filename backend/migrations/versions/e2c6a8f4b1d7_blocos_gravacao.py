"""Blocos de áudio da gravação de entrevista (v2.98).

Uma entrevista real dura 40–90 min. Gravar num arquivo único significa que uma
queda do navegador aos 32 minutos perde a conversa inteira — e ela não se refaz.
Os blocos (10 min por padrão, configurável) sobem durante a conversa: o que já
foi enviado está salvo.

Ver `models/bloco_gravacao.py` para o resto do desenho, incluindo por que a
ordem é o `indice` e nunca a listagem do storage.

Revision ID: e2c6a8f4b1d7
Revises: b8e2d4f6a1c3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "e2c6a8f4b1d7"
down_revision = "b8e2d4f6a1c3"
branch_labels = None
depends_on = None

VALORES = ("aguardando", "processando", "pronta", "falhou", "inaudivel")


def upgrade() -> None:
    enum = postgresql.ENUM(*VALORES, name="status_bloco_gravacao", create_type=False)
    enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bloco_gravacao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("gravacao_id", UUID(as_uuid=True),
                  sa.ForeignKey("gravacao_entrevista.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("indice", sa.Integer(), nullable=False),
        sa.Column("audio_key", sa.String(300)),
        sa.Column("audio_bytes", sa.Integer()),
        sa.Column("audio_tipo", sa.String(100)),
        sa.Column("duracao_s", sa.Integer()),
        sa.Column("inicio_s", sa.Integer()),
        sa.Column("status", enum, nullable=False, server_default="aguardando"),
        sa.Column("texto", sa.Text()),
        sa.Column("erro", sa.String(400)),
        sa.Column("transcrito_em", sa.DateTime(timezone=True)),
        sa.Column("processamento_s", sa.Integer()),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        # Reenviar o bloco 3 SUBSTITUI o anterior; sem isto, um upload repetido
        # (rede instável — o caso que os blocos existem para tratar) criaria um
        # bloco fantasma no meio da conversa.
        sa.UniqueConstraint("gravacao_id", "indice", name="uq_bloco_gravacao_indice"),
    )
    op.create_index("ix_bloco_gravacao_gravacao_id", "bloco_gravacao", ["gravacao_id"])
    op.create_index("ix_bloco_gravacao_status", "bloco_gravacao", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bloco_gravacao_status", table_name="bloco_gravacao")
    op.drop_index("ix_bloco_gravacao_gravacao_id", table_name="bloco_gravacao")
    op.drop_table("bloco_gravacao")
    postgresql.ENUM(name="status_bloco_gravacao").drop(op.get_bind(), checkfirst=True)
