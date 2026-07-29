"""Teste já respondido, aproveitado para um candidato (v2.21).

O RH vincula ao candidato um DISC/situacional ou uma prova que a pessoa já fez
antes de virar candidata. O vínculo APONTA para o resultado original (não
copia) e registra se a identidade foi deduzida pelo sistema (`automatico`) ou
afirmada por uma pessoa — o link avulso de testagem é anônimo, e homônimo
existe.

Revision ID: b8c9d0e1f2a3
Revises: a8b9c0d1e2f3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "b8c9d0e1f2a3"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None

# `.create(checkfirst=True)` + `create_type=False` no dialeto do Postgres —
# `sa.Enum` genérico dispararia CREATE TYPE de novo via evento DDL da tabela
# (armadilha registrada no CLAUDE.md).
_ORIGEM = postgresql.ENUM("testagem", "prova", name="origem_teste_vinculado",
                          create_type=False)


def upgrade() -> None:
    _ORIGEM.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "teste_vinculado",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("origem", _ORIGEM, nullable=False),
        sa.Column("participante_id", UUID(as_uuid=True),
                  sa.ForeignKey("participante_testagem.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("aplicacao_id", UUID(as_uuid=True),
                  sa.ForeignKey("aplicacao_prova.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("automatico", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("vinculado_por", sa.String(200), nullable=True),
        sa.Column("vinculado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("candidato_id", "participante_id",
                            name="uq_vinculo_participante"),
        sa.UniqueConstraint("candidato_id", "aplicacao_id",
                            name="uq_vinculo_aplicacao"),
    )


def downgrade() -> None:
    op.drop_table("teste_vinculado")
    _ORIGEM.drop(op.get_bind(), checkfirst=True)
