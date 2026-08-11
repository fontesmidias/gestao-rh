"""Data que os documentos não assinados carimbam (v2.89).

Nula para todo mundo: nulo significa "use o dia da geração", que é exatamente o
comportamento anterior. Ninguém tem a data de um documento alterada pelo deploy
— e é assim que tem de ser, porque documento é papel que circula.

Não há backfill possível nem desejável: adivinhar a data em que a integração de
alguém aconteceu reescreveria a data de um documento de gente real com um chute
(a mesma regra da data do creche, v2.27, e da capitalização de nomes, v2.54).
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a4c6b8d2f7"
down_revision = "d8f1c3a5b7e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidato", sa.Column("data_documentos", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidato", "data_documentos")
