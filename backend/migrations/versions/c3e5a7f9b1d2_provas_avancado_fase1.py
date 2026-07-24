"""Provas-avançado Fase 1: aleatorização + explicação.

- prova_cargo.embaralhar (bool) e .mostrar_explicacao (bool)
- questao_prova.explicacao (text)
- aplicacao_prova.seed (int) — semente do embaralhamento estável por participante

Sem enum. Colunas com default/nullable — seguras em base existente.

Revision ID: c3e5a7f9b1d2
Revises: b7c4d9e1f2a3
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op

revision = "c3e5a7f9b1d2"
down_revision = "b7c4d9e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prova_cargo", sa.Column(
        "embaralhar", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("prova_cargo", sa.Column(
        "mostrar_explicacao", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("questao_prova", sa.Column("explicacao", sa.Text(), nullable=True))
    op.add_column("aplicacao_prova", sa.Column("seed", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("aplicacao_prova", "seed")
    op.drop_column("questao_prova", "explicacao")
    op.drop_column("prova_cargo", "mostrar_explicacao")
    op.drop_column("prova_cargo", "embaralhar")
