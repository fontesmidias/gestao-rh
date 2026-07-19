"""Lixeira universal com retenção configurável (feedback de campo 2026-07-18).

Revision ID: e9b4c6d83f15
Revises: d8f3a5c72e91
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e9b4c6d83f15"
down_revision = "d8f3a5c72e91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_lixeira",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entidade", sa.String(length=40), nullable=False, index=True),
        sa.Column("entidade_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rotulo", sa.String(length=200), nullable=False),
        sa.Column("dados", sa.JSON(), nullable=False),
        sa.Column("ator", sa.String(length=200), nullable=True),
        sa.Column("apagado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("restaurado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("item_lixeira")
