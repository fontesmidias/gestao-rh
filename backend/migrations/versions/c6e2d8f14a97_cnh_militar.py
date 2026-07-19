"""CNH completa + situação militar na ficha (feedback de campo 2026-07-18).

Revision ID: c6e2d8f14a97
Revises: b3d9f5a82e17
"""
import sqlalchemy as sa
from alembic import op

revision = "c6e2d8f14a97"
down_revision = "b3d9f5a82e17"
branch_labels = None
depends_on = None

_TABELA = "documentos_identificacao"
_COLUNAS = [
    sa.Column("cnh_orgao_emissor", sa.String(length=40), nullable=True),
    sa.Column("cnh_uf", sa.String(length=2), nullable=True),
    sa.Column("cnh_data_emissao", sa.Date(), nullable=True),
    sa.Column("cnh_validade", sa.Date(), nullable=True),
    sa.Column("cnh_primeira_habilitacao", sa.Date(), nullable=True),
    sa.Column("militar_tipo", sa.String(length=30), nullable=True),
    sa.Column("militar_numero", sa.String(length=30), nullable=True),
    sa.Column("militar_serie", sa.String(length=20), nullable=True),
    sa.Column("militar_categoria", sa.String(length=30), nullable=True),
    sa.Column("militar_orgao", sa.String(length=80), nullable=True),
    sa.Column("militar_data_emissao", sa.Date(), nullable=True),
]


def upgrade() -> None:
    for col in _COLUNAS:
        op.add_column(_TABELA, col)


def downgrade() -> None:
    for col in reversed(_COLUNAS):
        op.drop_column(_TABELA, col.name)
