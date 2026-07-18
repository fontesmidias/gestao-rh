"""Posto: tirvu_id (chave natural do Tirvu) + razão social e endereço, para
importar a planilha de Postos do Tirvu casando/atualizando sem duplicar.

Revision ID: f9a3b7e21c46
Revises: e7c4a2f91d38
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a3b7e21c46"
down_revision = "e7c4a2f91d38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posto_servico", sa.Column("tirvu_id", sa.String(length=30), nullable=True))
    op.add_column("posto_servico", sa.Column("razao_social", sa.String(length=200), nullable=True))
    op.add_column("posto_servico", sa.Column("endereco", sa.String(length=300), nullable=True))
    op.add_column("posto_servico", sa.Column("cidade", sa.String(length=120), nullable=True))
    op.add_column("posto_servico", sa.Column("uf", sa.String(length=2), nullable=True))
    op.add_column("posto_servico", sa.Column("cep", sa.String(length=10), nullable=True))
    op.create_index("ix_posto_servico_tirvu_id", "posto_servico", ["tirvu_id"])


def downgrade() -> None:
    op.drop_index("ix_posto_servico_tirvu_id", table_name="posto_servico")
    op.drop_column("posto_servico", "cep")
    op.drop_column("posto_servico", "uf")
    op.drop_column("posto_servico", "cidade")
    op.drop_column("posto_servico", "endereco")
    op.drop_column("posto_servico", "razao_social")
    op.drop_column("posto_servico", "tirvu_id")
