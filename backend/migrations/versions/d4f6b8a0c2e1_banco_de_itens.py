"""Banco de itens (Provas Fase 2): tabela item_banco.

Questões REUTILIZÁVEIS catalogadas por cargo/senioridade/tags. ADITIVA — não
toca prova_cargo/questao_prova, então NÃO desmonta as provas existentes. Montar
prova a partir do banco copia o item para questao_prova (snapshot).

Revision ID: d4f6b8a0c2e1
Revises: c3e5a7f9b1d2
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d4f6b8a0c2e1"
down_revision = "c3e5a7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_banco",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("opcoes", sa.JSON(), nullable=True),
        sa.Column("gabarito", sa.String(40), nullable=True),
        sa.Column("explicacao", sa.Text(), nullable=True),
        sa.Column("peso", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cargo", sa.String(120), nullable=True),
        sa.Column("senioridade", sa.String(12), nullable=False, server_default="qualquer"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("criado_por", sa.String(200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_item_banco_cargo", "item_banco", ["cargo"])
    op.create_index("ix_item_banco_senioridade", "item_banco", ["senioridade"])


def downgrade() -> None:
    op.drop_index("ix_item_banco_senioridade", table_name="item_banco")
    op.drop_index("ix_item_banco_cargo", table_name="item_banco")
    op.drop_table("item_banco")
