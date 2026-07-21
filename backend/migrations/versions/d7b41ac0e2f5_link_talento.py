"""Link de testagem disparado para um talento do Banco de Talentos:
`talento_id` + `email_destino` no link_testagem, para enviar teste avulso ao
talento (sem convertê-lo) e trazer o resultado de volta ao dash.

Revision ID: d7b41ac0e2f5
Revises: c5a92e7b148d
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d7b41ac0e2f5"
down_revision = "c5a92e7b148d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("link_testagem",
                  sa.Column("talento_id", UUID(as_uuid=True),
                            sa.ForeignKey("talento.id"), nullable=True))
    op.add_column("link_testagem",
                  sa.Column("email_destino", sa.String(200), nullable=True))
    op.create_index("ix_link_testagem_talento_id", "link_testagem", ["talento_id"])


def downgrade() -> None:
    op.drop_index("ix_link_testagem_talento_id", table_name="link_testagem")
    op.drop_column("link_testagem", "email_destino")
    op.drop_column("link_testagem", "talento_id")
