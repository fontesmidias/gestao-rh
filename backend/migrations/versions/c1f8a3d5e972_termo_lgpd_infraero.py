"""Termo de consentimento LGPD (credenciamento INFRAERO) no kit de assinatura.

Revision ID: c1f8a3d5e972
Revises: b9e2f7a41c03
Create Date: 2026-07-15
"""

from alembic import op

revision = "c1f8a3d5e972"
down_revision = "b9e2f7a41c03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Novo valor no enum (não pode rodar em transação).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'termo_lgpd_infraero'")


def downgrade() -> None:
    # Valores de enum não são removidos (o Postgres não suporta DROP VALUE).
    pass
