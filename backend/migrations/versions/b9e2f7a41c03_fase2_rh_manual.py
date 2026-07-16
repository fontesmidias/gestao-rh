"""Fase 2 do feedback de campo: invalidação de assinatura (nunca deleção) e
origem do envio no slot (upload manual do RH etiquetado).

Revision ID: b9e2f7a41c03
Revises: a7d4e9c2b581
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op

revision = "b9e2f7a41c03"
down_revision = "a7d4e9c2b581"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assinatura",
                  sa.Column("invalidada_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assinatura",
                  sa.Column("invalidada_motivo", sa.String(300), nullable=True))
    op.add_column("slot_documento",
                  sa.Column("origem_envio", sa.String(20), nullable=True))
    op.add_column("slot_documento",
                  sa.Column("origem_envio_obs", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("slot_documento", "origem_envio_obs")
    op.drop_column("slot_documento", "origem_envio")
    op.drop_column("assinatura", "invalidada_motivo")
    op.drop_column("assinatura", "invalidada_em")
