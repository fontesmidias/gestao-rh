"""De-para lotação → posto de serviço (v2.40).

A planilha de colaboradores do Tirvu traz a lotação ABREVIADA ("INEP ADM",
"ANAC") e o apelido do posto aqui é o padrão longo ("ANAC - 14/2026 -
AEROPORTO"). Medido nos dados reais: 11% casam sozinhos, e "ANAC" pode ser
dois postos diferentes — ambiguidade do dado, não do algoritmo.

Esta tabela guarda a escolha que o RH confirmou, para as importações seguintes
não perguntarem de novo. Irmã de `cargo_tirvu`, mesma ideia: mapa lateral por
TEXTO, sem transformar lotação em entidade.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lotacao_tirvu",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lotacao_normalizada", sa.String(length=200), nullable=False),
        sa.Column("lotacao_rotulo", sa.String(length=200), nullable=False),
        sa.Column("posto_servico_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("posto_servico.id"), nullable=False),
        sa.Column("confirmado_por", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lotacao_tirvu_normalizada", "lotacao_tirvu",
                    ["lotacao_normalizada"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_lotacao_tirvu_normalizada", table_name="lotacao_tirvu")
    op.drop_table("lotacao_tirvu")
