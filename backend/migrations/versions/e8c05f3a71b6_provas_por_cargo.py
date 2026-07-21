"""Módulo de Provas por Cargo: banco de provas configurável pelo RH (questões
objetivas com gabarito no servidor + discursivas), aplicação por link avulso e
correção mista. Tabelas prova_cargo, questao_prova, link_prova, aplicacao_prova.

Revision ID: e8c05f3a71b6
Revises: d7b41ac0e2f5
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e8c05f3a71b6"
down_revision = "d7b41ac0e2f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prova_cargo",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("cargo", sa.String(120), nullable=True, index=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("tempo_segundos", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_por", sa.String(200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "questao_prova",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("prova_id", UUID(as_uuid=True),
                  sa.ForeignKey("prova_cargo.id"), nullable=False, index=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enunciado", sa.Text(), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("opcoes", sa.JSON(), nullable=True),
        sa.Column("gabarito", sa.String(40), nullable=True),
        sa.Column("peso", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "link_prova",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("prova_id", UUID(as_uuid=True),
                  sa.ForeignKey("prova_cargo.id"), nullable=False, index=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("talento_id", UUID(as_uuid=True),
                  sa.ForeignKey("talento.id"), nullable=True, index=True),
        sa.Column("email_destino", sa.String(200), nullable=True),
        sa.Column("criado_por", sa.String(200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "aplicacao_prova",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("link_id", UUID(as_uuid=True),
                  sa.ForeignKey("link_prova.id"), nullable=False, index=True),
        sa.Column("prova_id", UUID(as_uuid=True),
                  sa.ForeignKey("prova_cargo.id"), nullable=False, index=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("status", sa.String(14), nullable=False, server_default="pendente"),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prazo_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respostas", sa.JSON(), nullable=True),
        sa.Column("eventos", sa.JSON(), nullable=True),
        sa.Column("nota_objetivas", sa.Float(), nullable=True),
        sa.Column("nota_discursivas", sa.Float(), nullable=True),
        sa.Column("nota_final", sa.Float(), nullable=True),
        sa.Column("correcao_discursivas", sa.JSON(), nullable=True),
        sa.Column("corrigido_por", sa.String(200), nullable=True),
        sa.Column("corrigido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("aplicacao_prova")
    op.drop_table("link_prova")
    op.drop_table("questao_prova")
    op.drop_table("prova_cargo")
