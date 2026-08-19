"""Vigência do reembolso-creche por posto/contrato.

O e-mail do Jurídico (Dr. Lucas, 18/08/2026) lista os contratos com aditivo
assinado E A DATA em que cada um passou a valer: ANEEL 12/2026 desde 01/05/2026;
INEP 03/2026 e 37/2025 desde 01/08/2026; MAPA 58/2024 desde 01/08/2026;
PREPÚBLICA 62/2025 desde 01/02/2026.

Até aqui o direito era um booleano SEM data (`da_direito_creche`), então o
sistema não sabia responder *"esta pessoa tinha direito em maio?"* — pergunta que
aparece em retroativo e em resposta a auditoria do contratante. A data fica no
POSTO, ao lado do direito e do valor (decisão do Bruno, 2026-08-18): é lá que o
RH já marca as duas outras coisas, e um cadastro de contratos exigiria casar o
`contrato_ref`, que hoje é texto livre.

NULL = vigência não informada. NÃO se assume "vale desde sempre" nem "não vale":
adivinhar aqui decide dinheiro no contracheque de alguém, e o campo é novo para
todos — o RH preenche os cinco na tela de Postos.
"""

import sqlalchemy as sa
from alembic import op

revision = "a3f7c1e9d5b2"
down_revision = "e2c6a8f4b1d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("posto_servico",
                  sa.Column("creche_vigente_desde", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("posto_servico", "creche_vigente_desde")
