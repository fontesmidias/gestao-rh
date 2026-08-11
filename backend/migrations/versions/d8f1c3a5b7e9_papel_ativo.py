"""Papel pode ser ativado e desativado (v2.87).

`ativo` nasce `true` para todos: os papéis que já existem estão em uso, e um
default `false` cortaria o acesso de todo mundo no deploy — o oposto do que a
coluna existe para permitir. É a mesma regra do backfill da `c7e9a1b3d5f8`:
mudança de permissão que chega quebrando o trabalho de quem está no meio de uma
admissão é revertida às pressas.

O `server_default` é obrigatório porque a coluna é `NOT NULL` e a tabela já tem
linhas — sem ele o ALTER falha em qualquer banco com papel cadastrado, que é o
caso de toda instalação a partir da v2.86 (a lição da v2.70).
"""

import sqlalchemy as sa
from alembic import op

revision = "d8f1c3a5b7e9"
down_revision = "c7e9a1b3d5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("papel", sa.Column(
        "ativo", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("papel", "ativo")
