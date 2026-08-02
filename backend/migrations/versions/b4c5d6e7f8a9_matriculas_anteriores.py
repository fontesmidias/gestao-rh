"""Matrículas anteriores do colaborador (v2.45).

Feedback do Bruno em 2026-08-01: *"ter a opção de trocar o número da matrícula
de um admitido/colaborador"*.

O que torna a troca perigosa: o import de ponto do Tirvu casa a pessoa pela
MATRÍCULA (`desempenho.py::_casar_matricula`, normalizando zeros à esquerda).
Trocar o número desligaria a pessoa do próprio histórico de frequência, e uma
planilha de período anterior — que ainda traz a matrícula velha — deixaria de
casar. Silenciosamente, que é o pior jeito.

Guardar as matrículas antigas resolve os dois lados: o histórico segue a pessoa
e a reimportação de um período antigo continua encontrando quem é.

Lista, e não campo único: ninguém troca de matrícula uma vez só na vida
(recontratação, correção de digitação, fusão de cadastro).

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidato",
                  sa.Column("matriculas_anteriores", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidato", "matriculas_anteriores")
