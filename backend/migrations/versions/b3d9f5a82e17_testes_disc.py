"""Testes do candidato: inventário DISC e teste situacional (TesteCandidato).

Revision ID: b3d9f5a82e17
Revises: a1c8e4f70b23
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3d9f5a82e17"
down_revision = "a1c8e4f70b23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tipo = postgresql.ENUM("disc", "situacional", name="tipo_teste")
    tipo.create(op.get_bind(), checkfirst=True)
    status = postgresql.ENUM("pendente", "em_andamento", "concluido", "expirado",
                             name="status_teste")
    status.create(op.get_bind(), checkfirst=True)
    tipo_col = postgresql.ENUM("disc", "situacional", name="tipo_teste", create_type=False)
    status_col = postgresql.ENUM("pendente", "em_andamento", "concluido", "expirado",
                                 name="status_teste", create_type=False)

    op.create_table(
        "teste_candidato",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False),
        sa.Column("tipo", tipo_col, nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="pendente"),
        sa.Column("identificado_em", sa.DateTime(timezone=True)),
        sa.Column("codigo_hash", sa.String(64)),
        sa.Column("codigo_expira_em", sa.DateTime(timezone=True)),
        sa.Column("iniciado_em", sa.DateTime(timezone=True)),
        sa.Column("prazo_ate", sa.DateTime(timezone=True)),
        sa.Column("concluido_em", sa.DateTime(timezone=True)),
        sa.Column("respostas", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resultado", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("aceite_em", sa.DateTime(timezone=True)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_teste_candidato_candidato_id", "teste_candidato", ["candidato_id"])


def downgrade() -> None:
    op.drop_table("teste_candidato")
    postgresql.ENUM(name="status_teste").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="tipo_teste").drop(op.get_bind(), checkfirst=True)
