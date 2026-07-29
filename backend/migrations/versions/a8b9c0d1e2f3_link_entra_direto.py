"""Link do e-mail entra direto (v2.17): `link_expira_em` no acesso do creche
e do portal.

O código de 6 dígitos e o link chegam no MESMO e-mail — logo, provam o MESMO
fator (posse da caixa). Exigir os dois era atrito duplicado, e travou o RH em
campo (2026-07-29). Agora o link entra sozinho enquanto `link_expira_em` não
vence (15 min, igual ao código); a sessão que ele abre continua com as 6h de
`expira_em`.

Nulo = acesso antigo, que segue exigindo o código — nenhum link já emitido
muda de comportamento.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabela in ("acesso_creche", "acesso_portal"):
        op.add_column(tabela, sa.Column("link_expira_em",
                                        sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for tabela in ("acesso_creche", "acesso_portal"):
        op.drop_column(tabela, "link_expira_em")
