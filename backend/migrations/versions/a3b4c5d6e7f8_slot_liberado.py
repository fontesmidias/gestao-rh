"""Slot liberado pelo RH para envio tardio (v2.43).

Feedback do Bruno em 2026-08-01: um colaborador é PCD, não declarou no
formulário (dado de saúde — muita gente evita) e informou o RH por fora.

O RH sempre pôde marcar `pcd` na ficha. O problema aparece um passo adiante: ao
marcar, `slots.py` cria o slot do LAUDO como obrigatório — e se a pessoa já
concluiu o envio ou já foi aprovada, o checklist dela está congelado. Resultado:
o RH faz a coisa certa e ganha um documento obrigatório que ninguém consegue
preencher.

Estas colunas autorizam o envio daquele slot ESPECÍFICO, sem reabrir a
admissão inteira — a mesma ideia da reabertura cirúrgica de 2026-07-24, agora
para um documento que nasceu depois. Guardam quem liberou e quando, porque
abrir uma porta fechada é ato que precisa de dono.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("slot_documento",
                  sa.Column("liberado_em", sa.DateTime(timezone=True), nullable=True))
    op.add_column("slot_documento",
                  sa.Column("liberado_por", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("slot_documento", "liberado_por")
    op.drop_column("slot_documento", "liberado_em")
