"""Acordo de confidencialidade como ficha de TODOS os candidatos.

Revision ID: d4a9c6e1f358
Revises: c1f8a3d5e972
Create Date: 2026-07-16
"""

from alembic import op

revision = "d4a9c6e1f358"
down_revision = "c1f8a3d5e972"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'acordo_confidencialidade'")


def downgrade() -> None:
    # Valores de enum não são removidos (o Postgres não suporta DROP VALUE).
    pass
