"""Carteira de Processos do RH (v2.91).

Três tabelas ADITIVAS: `funcao_rh` (quem possui processos — o CARGO, não a
pessoa), `processo_rh` (o que é feito) e `atribuicao_processo` (a cadeia de
responsabilidade, uma linha por posição e cenário).

Nasce VAZIA de propósito. A carteira entra pela importação da planilha do
Bruno, com prévia e confirmação — semear 31 processos aqui os deixaria sem
caminho de atualização quando a planilha fosse revista (ela é revisada a cada
trimestre), e "só serve uma vez" é o oposto do que o módulo precisa ser.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3c6e8f1b4d7"
down_revision = "f2b5d7c9e3a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funcao_rh",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False, unique=True),
        sa.Column("descricao", sa.String(400), nullable=True),
        sa.Column("pessoa_nome", sa.String(200), nullable=True),
        sa.Column("pessoa_email", sa.String(200), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "processo_rh",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("codigo", sa.String(20), nullable=False, unique=True),
        sa.Column("fase", sa.String(120), nullable=False),
        sa.Column("nome", sa.String(300), nullable=False),
        sa.Column("ritmo", sa.String(40), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("aprovadores", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("consultados", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("informados", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_processo_rh_codigo", "processo_rh", ["codigo"], unique=True)

    op.create_table(
        "atribuicao_processo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("processo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("processo_rh.id", ondelete="CASCADE"), nullable=False),
        sa.Column("funcao_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("funcao_rh.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cenario", sa.String(4), nullable=False, server_default="C1"),
        sa.Column("posicao", sa.Integer(), nullable=False),
        # Dois titulares do mesmo processo no mesmo cenário passariam
        # despercebidos, e "quem responde por isto?" teria duas respostas — que
        # é o mesmo que não ter nenhuma.
        sa.UniqueConstraint("processo_id", "cenario", "posicao",
                            name="uq_atribuicao_posicao"),
    )
    op.create_index("ix_atribuicao_processo", "atribuicao_processo", ["processo_id"])
    op.create_index("ix_atribuicao_funcao", "atribuicao_processo", ["funcao_id"])
    op.create_index("ix_atribuicao_cenario", "atribuicao_processo", ["cenario"])


def downgrade() -> None:
    op.drop_table("atribuicao_processo")
    op.drop_index("ix_processo_rh_codigo", table_name="processo_rh")
    op.drop_table("processo_rh")
    op.drop_table("funcao_rh")
