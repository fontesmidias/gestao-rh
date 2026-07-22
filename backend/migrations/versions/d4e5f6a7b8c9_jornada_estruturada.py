"""Jornadas estruturadas (feedback 2026-07-22): metadados internos por cima da
`descricao` canônica (que continua sendo o que vai ao Tirvu). Campos de escala,
4 horários, bloco secundário, turno/adicional noturno, intrajornada (+obs),
cargo relacionado e o carimbo de confirmação da estruturação. Todos NULLABLE —
não quebram as jornadas existentes.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


COLS = [
    ("escala", sa.String(20)),
    ("hora_entrada", sa.String(5)),
    ("saida_almoco", sa.String(5)),
    ("volta_almoco", sa.String(5)),
    ("hora_saida", sa.String(5)),
    ("bloco_secundario", sa.String(150)),
    ("turno", sa.String(10)),
    ("intrajornada_obs", sa.String(60)),
    ("cargo_relacionado", sa.String(40)),
    ("estruturado_confirmado_em", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    for nome, tipo in COLS:
        op.add_column("jornada", sa.Column(nome, tipo, nullable=True))
    op.add_column("jornada", sa.Column("adicional_noturno", sa.Boolean(),
                                       nullable=False, server_default=sa.false()))
    op.add_column("jornada", sa.Column("tem_intrajornada", sa.Boolean(),
                                       nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for nome in ("tem_intrajornada", "adicional_noturno", *[c for c, _ in COLS]):
        op.drop_column("jornada", nome)
