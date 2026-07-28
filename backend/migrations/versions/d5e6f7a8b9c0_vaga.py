"""Vaga (v1.99, Match de Vagas × Banco de Talentos).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vaga",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("requisitos_obrigatorios", sa.Text(), nullable=True),
        sa.Column("requisitos_desejaveis", sa.Text(), nullable=True),
        sa.Column("cargo", sa.String(length=120), nullable=True),
        sa.Column("regiao", sa.String(length=120), nullable=True),
        sa.Column("regime", sa.String(length=20), nullable=True),
        sa.Column("salario_min", sa.String(length=30), nullable=True),
        sa.Column("salario_max", sa.String(length=30), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("vaga")
