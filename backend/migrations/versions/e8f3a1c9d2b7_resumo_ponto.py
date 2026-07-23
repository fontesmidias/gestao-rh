"""Resumo de ponto (frequência do Tirvu) por pessoa/período — CONTEXTO para a
avaliação, não nota. Upload manual do .xlsx.

Revision ID: e8f3a1c9d2b7
Revises: c7d2e8f4a916
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# id conferido único (grep em migrations/versions/): reusar fecha ciclo no
# Alembic e derruba o upgrade em produção.
revision = "e8f3a1c9d2b7"
down_revision = "c7d2e8f4a916"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resumo_ponto",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id")),
        sa.Column("matricula", sa.String(30)),
        sa.Column("nome_planilha", sa.String(200)),
        sa.Column("periodo_inicio", sa.Date(), nullable=False),
        sa.Column("periodo_fim", sa.Date(), nullable=False),
        sa.Column("dias_com_registro", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutos_trabalhados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minutos_previstos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("faltas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incompletos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dias_abaixo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dias_acima", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detalhe", sa.JSON()),
        sa.Column("importado_por", sa.String(200)),
        sa.Column("importado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_resumo_ponto_candidato_id", "resumo_ponto", ["candidato_id"])
    op.create_index("ix_resumo_ponto_matricula", "resumo_ponto", ["matricula"])
    op.create_index("ix_resumo_ponto_periodo_inicio", "resumo_ponto", ["periodo_inicio"])
    op.create_index("ix_resumo_ponto_periodo_fim", "resumo_ponto", ["periodo_fim"])


def downgrade() -> None:
    op.drop_table("resumo_ponto")
