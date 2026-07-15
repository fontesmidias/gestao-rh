"""Convite sem e-mail: email e celular do candidato passam a ser opcionais.

Revision ID: f3b8c2d91a44
Revises: e1a95c7f3b20
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op

revision = "f3b8c2d91a44"
down_revision = "e1a95c7f3b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("candidato", "email", existing_type=sa.String(200), nullable=True)
    op.alter_column("candidato", "celular_whatsapp", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE candidato SET email = '' WHERE email IS NULL")
    op.execute("UPDATE candidato SET celular_whatsapp = '' WHERE celular_whatsapp IS NULL")
    op.alter_column("candidato", "celular_whatsapp", existing_type=sa.String(20), nullable=False)
    op.alter_column("candidato", "email", existing_type=sa.String(200), nullable=False)
