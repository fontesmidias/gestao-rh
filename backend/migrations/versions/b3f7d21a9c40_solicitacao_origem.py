"""Coluna `origem` na solicitacao_assinatura: identifica roteiros de assinatura
gerados por módulos específicos (ex.: 'creche_requerimento') para escolher o
gerador de PDF correto na consolidação, sem depender de heurística de título.

Revision ID: b3f7d21a9c40
Revises: a1e6c9d24f78
Create Date: 2026-07-20
"""

import sqlalchemy as sa
from alembic import op

revision = "b3f7d21a9c40"
down_revision = "a1e6c9d24f78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("solicitacao_assinatura",
                  sa.Column("origem", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("solicitacao_assinatura", "origem")
