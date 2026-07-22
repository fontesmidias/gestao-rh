"""Reembolso-Creche: declaração "não faço jus" (feedback 2026-07-21). Novo
valor de status `sem_direito_declarado` + colunas sem_direito_em/por. O
colaborador declara no link (ou o RH registra pelo painel) que não tem
dependentes que dão direito — some da fila de ação, fica no relatório.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE não roda dentro de transação; commita antes.
    op.execute("COMMIT")
    op.execute("ALTER TYPE status_beneficio ADD VALUE IF NOT EXISTS 'sem_direito_declarado'")
    op.add_column("beneficio_creche",
                  sa.Column("sem_direito_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("beneficio_creche",
                  sa.Column("sem_direito_por", sa.String(200), nullable=True))


def downgrade() -> None:
    # Não há DROP VALUE em enum Postgres; removemos só as colunas.
    op.drop_column("beneficio_creche", "sem_direito_por")
    op.drop_column("beneficio_creche", "sem_direito_em")
