"""nome social nos dados pessoais (Decreto 8.727/2016)

Revision ID: c4f7d2ab8810
Revises: 9c30ab41de55
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op

revision = "c4f7d2ab8810"
down_revision = "9c30ab41de55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dados_pessoais", sa.Column("nome_social", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("dados_pessoais", "nome_social")
