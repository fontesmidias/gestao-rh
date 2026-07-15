"""filiação (mãe e pai) nos dados pessoais — pai omitível (não declarado)

Revision ID: e1a95c7f3b20
Revises: c4f7d2ab8810
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a95c7f3b20"
down_revision = "c4f7d2ab8810"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dados_pessoais", sa.Column("nome_mae", sa.String(200), nullable=True))
    op.add_column("dados_pessoais", sa.Column("nome_pai", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("dados_pessoais", "nome_pai")
    op.drop_column("dados_pessoais", "nome_mae")
