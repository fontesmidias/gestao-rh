"""Tirvu casa por ID numérico, não por texto (feedback de campo 2026-07-24):
tirvu_id em empresa e jornada + tabela de-para cargo_tirvu (cargo texto → id).
O export de admissões passa a escrever os IDs; falta de ID vira pendência.

Revision ID: a7b3c9d1e2f4
Revises: e6a8c0d2f4b1
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a7b3c9d1e2f4"
down_revision = "e6a8c0d2f4b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("empresa", sa.Column("tirvu_id", sa.String(length=30), nullable=True))
    op.add_column("jornada", sa.Column("tirvu_id", sa.String(length=30), nullable=True))
    op.create_table(
        "cargo_tirvu",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cargo_normalizado", sa.String(length=160), nullable=False),
        sa.Column("cargo_rotulo", sa.String(length=160), nullable=False),
        sa.Column("tirvu_id", sa.String(length=30), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cargo_tirvu_cargo_normalizado", "cargo_tirvu",
                    ["cargo_normalizado"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_cargo_tirvu_cargo_normalizado", table_name="cargo_tirvu")
    op.drop_table("cargo_tirvu")
    op.drop_column("jornada", "tirvu_id")
    op.drop_column("empresa", "tirvu_id")
