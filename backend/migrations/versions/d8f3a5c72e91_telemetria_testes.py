"""Telemetria dos testes + flag "na Domínio" (feedback de campo 2026-07-18).

Revision ID: d8f3a5c72e91
Revises: c6e2d8f14a97
"""
import sqlalchemy as sa
from alembic import op

revision = "d8f3a5c72e91"
down_revision = "c6e2d8f14a97"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teste_candidato",
                  sa.Column("eventos", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("candidato",
                  sa.Column("na_dominio_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("candidato", "na_dominio_em")
    op.drop_column("teste_candidato", "eventos")
