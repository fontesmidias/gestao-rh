"""Reembolso-Creche: devolução do levantamento para correção (feedback
2026-07-21). O RH devolve com um motivo VISÍVEL ao colaborador; o status volta
a `levantamento` e ele reenvia. Campos motivo_devolucao + devolvido_em no
beneficio_creche (distintos do motivo_indeferimento, que é terminal).

Revision ID: f1a2b3c4d5e6
Revises: e8c05f3a71b6
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e8c05f3a71b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("beneficio_creche",
                  sa.Column("motivo_devolucao", sa.String(400), nullable=True))
    op.add_column("beneficio_creche",
                  sa.Column("devolvido_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("beneficio_creche", "devolvido_em")
    op.drop_column("beneficio_creche", "motivo_devolucao")
