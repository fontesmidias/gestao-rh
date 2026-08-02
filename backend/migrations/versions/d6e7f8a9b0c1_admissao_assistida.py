"""Admissão presencial assistida (v2.56).

Feedback de campo 2026-08-02: *"quero pensar em uma estratégia para os casos em
que a pessoa tiver baixo grau de instrução, ou dificuldades, para que elas
quando chegarem na empresa, o RH fazer tudo [...] e ver alguma forma que a
pessoa possa assinar o documento"*.

Duas colunas, as duas SNAPSHOT de e-mail (nunca FK — a evidência não pode sumir
se o usuário do RH for removido depois):

* `acesso_magico.assistido_por` — marca o LINK como emitido para uma sessão
  assistida. A marca vive no link porque o wizard já resolve o token a cada
  requisição; uma tabela de sessão à parte precisaria ser sincronizada e
  encerrada, e sessão esquecida aberta seria pior que não ter o recurso.
* `assinatura.assistida_por` — quem operou o preenchimento quando aquela
  assinatura foi colhida. É o que permite ao manifesto descrever o ato como
  ele foi, em vez de afirmar que a pessoa assinou sozinha na plataforma.

Aditiva e nulável: nada muda para as admissões existentes, e `NULL` significa
exatamente o que sempre significou — assinatura remota, feita pela própria
pessoa.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""
import sqlalchemy as sa
from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("acesso_magico",
                  sa.Column("assistido_por", sa.String(length=200), nullable=True))
    op.add_column("assinatura",
                  sa.Column("assistida_por", sa.String(length=200), nullable=True))


def downgrade() -> None:
    # `assinatura.assistida_por` é EVIDÊNCIA de um ato de assinatura — apagá-la
    # remove do registro a informação de que o preenchimento foi assistido, que
    # é justamente o que o manifesto declara. Faça `pg_dump` antes.
    op.drop_column("assinatura", "assistida_por")
    op.drop_column("acesso_magico", "assistido_por")
