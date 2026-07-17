"""Banco de Talentos: cadastro público de interessados, triagem pelo RH e
conversão em candidato.

Revision ID: a9d3f6b18c42
Revises: f7c2a9d4e611
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a9d3f6b18c42"
down_revision = "f7c2a9d4e611"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM("novo", "em_analise", "convertido", "arquivado",
                             name="status_talento", create_type=False)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "talento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=True, index=True),
        sa.Column("telefone", sa.String(20), nullable=True),
        sa.Column("cargo_interesse", sa.String(120), nullable=True, index=True),
        sa.Column("cidade", sa.String(120), nullable=True),
        sa.Column("escolaridade", sa.String(60), nullable=True),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("origem", sa.String(80), nullable=True),
        sa.Column("status", status, nullable=False, server_default="novo", index=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("talento")
    postgresql.ENUM(name="status_talento").drop(op.get_bind(), checkfirst=True)
