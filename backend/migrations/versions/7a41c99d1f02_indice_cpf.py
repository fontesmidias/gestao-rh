"""índice de CPF para o portal de retorno (/entrar)

Revision ID: 7a41c99d1f02
Revises: 2e0b818e2324
Create Date: 2026-07-15
"""

from alembic import op

revision = "7a41c99d1f02"
down_revision = "2e0b818e2324"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Não-único de propósito: recontratações criam um novo processo com o mesmo CPF.
    op.create_index("ix_documentos_identificacao_cpf", "documentos_identificacao", ["cpf"])


def downgrade() -> None:
    op.drop_index("ix_documentos_identificacao_cpf", table_name="documentos_identificacao")
