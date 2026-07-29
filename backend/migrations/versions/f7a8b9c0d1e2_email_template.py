"""Textos de e-mail editáveis pelo RH (v2.06): a versão vigente por chave e o
histórico append-only de quem mudou o quê, com restauração.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_template",
        sa.Column("chave", sa.String(80), primary_key=True),
        sa.Column("assunto", sa.Text(), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("botao_texto", sa.String(80), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_por", sa.String(200), nullable=True),
    )
    op.create_table(
        "email_template_versao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("chave", sa.String(80), nullable=False, index=True),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("assunto", sa.Text(), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("botao_texto", sa.String(80), nullable=True),
        sa.Column("autor", sa.String(200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("chave", "versao", name="uq_email_versao"),
    )


def downgrade() -> None:
    op.drop_table("email_template_versao")
    op.drop_table("email_template")
