"""Postos: sigla, CNPJ, atributos dinâmicos e 'ativo' (CRUD + importador).

Revision ID: b2e6f8c31d05
Revises: a9d3f6b18c42
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "b2e6f8c31d05"
down_revision = "a9d3f6b18c42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posto_servico", sa.Column("sigla", sa.String(60), nullable=True))
    op.add_column("posto_servico", sa.Column("cnpj", sa.String(20), nullable=True))
    op.add_column("posto_servico",
                  sa.Column("atributos", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("posto_servico",
                  sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("posto_servico", "ativo")
    op.drop_column("posto_servico", "atributos")
    op.drop_column("posto_servico", "cnpj")
    op.drop_column("posto_servico", "sigla")
