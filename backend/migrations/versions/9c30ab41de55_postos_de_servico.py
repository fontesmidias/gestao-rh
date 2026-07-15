"""postos de serviço e documentos assináveis adicionais (INFRAERO)

Revision ID: 9c30ab41de55
Revises: 7a41c99d1f02
Create Date: 2026-07-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "9c30ab41de55"
down_revision = "7a41c99d1f02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posto_servico",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False, unique=True),
        sa.Column("contrato_ref", sa.String(200)),
        sa.Column("exige_docs_infraero", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.add_column("candidato", sa.Column(
        "posto_servico_id", UUID(as_uuid=True),
        sa.ForeignKey("posto_servico.id"), nullable=True))
    op.add_column("candidato", sa.Column("cargo_funcao", sa.String(120), nullable=True))

    # Novos valores no enum de documentos assináveis (não pode rodar em transação).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'oficio_cartao_cidadao'")
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'informacoes_trabalhador'")


def downgrade() -> None:
    # Valores de enum não são removidos (o Postgres não suporta DROP VALUE).
    op.drop_column("candidato", "cargo_funcao")
    op.drop_column("candidato", "posto_servico_id")
    op.drop_table("posto_servico")
