"""Decisão do RH por CRIANÇA no reembolso-creche (v2.55).

Feedback de campo 2026-08-02: *"se a pessoa tem mais de um filho e um eu defiro
e outro eu indefiro, não tem opção individual por filho, somente indeferir tudo
ou aprovar tudo"*.

Migração ADITIVA: só acrescenta colunas nuláveis em `crianca_creche`. Não toca
em nenhum registro existente e não muda o `beneficio_creche`.

**Por que NÃO se faz backfill**: marcar as crianças de benefícios já ativos como
`deferida` gravaria uma decisão que ninguém tomou, com data e autor inventados —
num campo que é justamente prova de ato administrativo. `NULL` significa
"decidida pelo modelo anterior, no benefício inteiro", e o código trata esse
caso explicitamente (ver `_dump_crianca_rh` e `ativar_beneficio`). É a mesma
regra da data do creche e dos nomes em caixa alta: não se reescreve dado de
gente real por conveniência de código.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""
import sqlalchemy as sa
from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("crianca_creche",
                  sa.Column("decisao", sa.String(length=12), nullable=True))
    op.add_column("crianca_creche",
                  sa.Column("motivo_decisao", sa.String(length=400), nullable=True))
    op.add_column("crianca_creche",
                  sa.Column("decidido_por", sa.String(length=200), nullable=True))
    op.add_column("crianca_creche",
                  sa.Column("decidido_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Descartar estas colunas apaga decisões do RH — que são registro de ato
    # administrativo, com autor e data. O downgrade existe para destravar um
    # deploy ruim; se for usado depois de o RH já ter decidido por criança,
    # faça `pg_dump` antes (a regra geral do CHANGELOG).
    op.drop_column("crianca_creche", "decidido_em")
    op.drop_column("crianca_creche", "decidido_por")
    op.drop_column("crianca_creche", "motivo_decisao")
    op.drop_column("crianca_creche", "decisao")
