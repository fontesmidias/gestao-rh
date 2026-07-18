"""Kit de documentos por posto (documentos_kit) + fichas específicas da
Presidência da República como documentos assináveis.

Revision ID: d5a1b8f34c92
Revises: c3f9a7d21e68
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "d5a1b8f34c92"
down_revision = "c3f9a7d21e68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'ficha_cadastral_terceirizado'")
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'oficio_apresentacao_presidencia'")
    op.add_column("posto_servico",
                  sa.Column("documentos_kit", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("posto_servico", "documentos_kit")
