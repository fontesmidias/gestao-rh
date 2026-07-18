"""Regime do colaborador (efetivo/intermitente) e o Informativo de Integração
do intermitente como documento assinável.

Revision ID: c3f9a7d21e68
Revises: b2e6f8c31d05
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "c3f9a7d21e68"
down_revision = "b2e6f8c31d05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Novo documento assinável (enum precisa de autocommit no Postgres).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'informativo_intermitente'")
    op.add_column("candidato",
                  sa.Column("regime", sa.String(20), nullable=False, server_default="efetivo"))


def downgrade() -> None:
    op.drop_column("candidato", "regime")
