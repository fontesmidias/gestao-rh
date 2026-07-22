"""Limpar a colisão de status (feedback 2026-07-21, item 1b), PARTE 1/2: só
ADICIONA o valor `importado` ao enum status_candidato. A migração de DADOS que
USA esse valor fica na revisão seguinte — o Postgres proíbe usar um valor de
enum recém-criado na MESMA transação em que foi adicionado
(UnsafeNewEnumValueUsage), então o UPDATE precisa de uma transação posterior.

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-07-21
"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")  # ADD VALUE não roda dentro de transação
    op.execute("ALTER TYPE status_candidato ADD VALUE IF NOT EXISTS 'importado'")


def downgrade() -> None:
    pass  # não há DROP VALUE em enum Postgres
