"""Edição de anotação do CRM (feedback 2026-07-27, item B2): o autor original
nunca é sobrescrito por quem edita depois — campos aditivos de editor+data.

Revision ID: b3c4d5e6f7a8
Revises: a7b3c9d1e2f4
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a7b3c9d1e2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crm_anotacao", sa.Column("editado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crm_anotacao", sa.Column("editor_nome", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("crm_anotacao", "editor_nome")
    op.drop_column("crm_anotacao", "editado_em")
