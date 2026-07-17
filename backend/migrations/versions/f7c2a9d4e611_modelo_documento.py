"""Modelos de documento criados pelo RH (CRUD): documento com layout timbrado,
variáveis dinâmicas e vínculo a cargo, posto ou colaborador.

Revision ID: f7c2a9d4e611
Revises: e5b1c4d7a209
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f7c2a9d4e611"
down_revision = "e5b1c4d7a209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    escopo = postgresql.ENUM("avulso", "cargo", "posto", "colaborador",
                             name="escopo_modelo", create_type=False)
    escopo.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "modelo_documento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("escopo", escopo, nullable=False, server_default="avulso"),
        sa.Column("cargo_alvo", sa.String(120), nullable=True),
        sa.Column("posto_alvo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("posto_servico.id"), nullable=True),
        sa.Column("candidato_alvo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("modelo_documento")
    postgresql.ENUM(name="escopo_modelo").drop(op.get_bind(), checkfirst=True)
