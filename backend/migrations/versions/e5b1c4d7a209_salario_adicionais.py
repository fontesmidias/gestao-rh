"""Remuneração do colaborador na ficha: salário base (texto livre, o RH digita)
e adicionais (lista nome + valor em R$ ou %). Por ora sem tabela de cargos —
o RH preenche à mão; a estrutura já prevê salário por cargo para o futuro.

Revision ID: e5b1c4d7a209
Revises: d4a9c6e1f358
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b1c4d7a209"
down_revision = "d4a9c6e1f358"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidato", sa.Column("salario_base", sa.String(60), nullable=True))
    op.add_column("candidato",
                  sa.Column("adicionais", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("candidato", "adicionais")
    op.drop_column("candidato", "salario_base")
