"""Ciência do cartão de mobilidade (GO): registro de quando o colaborador
declarou ciência de que a empresa solicitará o(s) cartão(ões) vinculados ao CNPJ.

Revision ID: a7d4e9c2b581
Revises: f3b8c2d91a44
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op

revision = "a7d4e9c2b581"
down_revision = "f3b8c2d91a44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vale_transporte",
                  sa.Column("ciencia_cartao_go_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vale_transporte", "ciencia_cartao_go_em")
