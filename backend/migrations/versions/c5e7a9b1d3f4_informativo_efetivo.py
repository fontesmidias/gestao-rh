"""Informativo de Integração do EFETIVO como documento assinável.

Até aqui só o intermitente tinha ficha de integração: `gerar_docs_do_posto_e_regime`
só acrescentava documento quando `regime == "intermitente"`, então o efetivo — a
maioria — não recebia nenhuma. O que existia com nome parecido
(`informacoes_trabalhador`) é outra coisa: um ofício de direitos do kit INFRAERO.

Só ADICIONA o valor ao enum; quem o usa é a revisão seguinte (o Postgres proíbe
usar valor de enum recém-criado na mesma transação — ver CLAUDE.md).

Revision ID: c5e7a9b1d3f4
Revises: b2d4f6a8c1e3
Create Date: 2026-08-05
"""

from alembic import op

revision = "c5e7a9b1d3f4"
down_revision = "b2d4f6a8c1e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE documento_assinavel ADD VALUE IF NOT EXISTS "
                   "'informativo_efetivo'")


def downgrade() -> None:
    # O Postgres não remove valor de enum sem recriar o tipo; o valor fica órfão
    # (mesmo tratamento dos valores órfãos de StatusCandidato).
    pass
