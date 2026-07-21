"""Banco de Talentos repaginado: campos do Forms (cargos/regiões múltiplos, tipo
de contratação, já-trabalhou, seguro-desemprego, consentimento LGPD) e currículo
opcional (arquivo no MinIO). Todas as colunas nullable — registros existentes
seguem válidos.

Revision ID: c5a92e7b148d
Revises: b3f7d21a9c40
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "c5a92e7b148d"
down_revision = "b3f7d21a9c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("talento", sa.Column("cargos_interesse", sa.JSON(), nullable=True))
    op.add_column("talento", sa.Column("regioes", sa.JSON(), nullable=True))
    op.add_column("talento", sa.Column("tipo_contratacao", sa.String(20), nullable=True))
    op.add_column("talento", sa.Column("ja_trabalhou_funcao", sa.Boolean(), nullable=True))
    op.add_column("talento", sa.Column("recebe_seguro_desemprego", sa.Boolean(), nullable=True))
    op.add_column("talento", sa.Column("consentimento_lgpd_em",
                                       sa.DateTime(timezone=True), nullable=True))
    op.add_column("talento", sa.Column("curriculo_key", sa.String(300), nullable=True))
    op.add_column("talento", sa.Column("curriculo_nome", sa.String(200), nullable=True))
    op.add_column("talento", sa.Column("curriculo_tipo", sa.String(100), nullable=True))


def downgrade() -> None:
    for col in ("curriculo_tipo", "curriculo_nome", "curriculo_key",
                "consentimento_lgpd_em", "recebe_seguro_desemprego",
                "ja_trabalhou_funcao", "tipo_contratacao", "regioes",
                "cargos_interesse"):
        op.drop_column("talento", col)
