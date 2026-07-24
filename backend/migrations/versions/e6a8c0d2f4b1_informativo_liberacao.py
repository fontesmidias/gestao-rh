"""Leva admissão/ficha: informativo com liberação do RH + autodeclaração de
residência (comprovante de terceiro).

- assinatura.aguardando_liberacao (bool): informativo nasce True (oculto até o
  RH liberar); demais docs False (inalterado).
- endereco.comprovante_titular / comprovante_relacao: quando o comprovante não
  está no nome do candidato — dispara a autodeclaração.
- enum documento_assinavel += 'autodeclaracao_residencia'.

Revision ID: e6a8c0d2f4b1
Revises: d4f6b8a0c2e1
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op

revision = "e6a8c0d2f4b1"
down_revision = "d4f6b8a0c2e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assinatura", sa.Column(
        "aguardando_liberacao", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("endereco", sa.Column("comprovante_titular", sa.String(200), nullable=True))
    op.add_column("endereco", sa.Column("comprovante_relacao", sa.String(80), nullable=True))
    # Novo valor de enum — fora de transação (o valor NÃO é usado nesta migration,
    # só passa a ser referenciável; sem UnsafeNewEnumValueUsage).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'autodeclaracao_residencia'")


def downgrade() -> None:
    # Valor de enum não é removido (Postgres não suporta DROP VALUE).
    op.drop_column("endereco", "comprovante_relacao")
    op.drop_column("endereco", "comprovante_titular")
    op.drop_column("assinatura", "aguardando_liberacao")
