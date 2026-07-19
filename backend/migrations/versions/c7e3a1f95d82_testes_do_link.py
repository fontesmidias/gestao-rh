"""Link de testagem escolhe quais testes aplica (DISC / situacional / ambos).

Default True nos dois: links existentes seguem oferecendo os dois testes.

Revision ID: c7e3a1f95d82
Revises: b6d1f4a82c39
"""
import sqlalchemy as sa
from alembic import op

revision = "c7e3a1f95d82"
down_revision = "b6d1f4a82c39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("link_testagem", sa.Column(
        "tem_disc", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("link_testagem", sa.Column(
        "tem_situacional", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("link_testagem", "tem_situacional")
    op.drop_column("link_testagem", "tem_disc")
