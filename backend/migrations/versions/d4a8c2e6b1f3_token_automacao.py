"""Tabela `token_automacao` — credencial de máquina do MCP (v2.94).

Ver `app/models/token_automacao.py` para o desenho. O essencial: o segredo NÃO
é guardado, só o `sha256`; revogar é marcar `revogado_em`, nunca apagar a linha.

Revision ID: d4a8c2e6b1f3
Revises: c3f7b1d9e4a2
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d4a8c2e6b1f3"
down_revision = "c3f7b1d9e4a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "token_automacao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", UUID(as_uuid=True),
                  sa.ForeignKey("usuario_rh.id", ondelete="CASCADE"), nullable=False),
        sa.Column("descricao", sa.String(200), nullable=False),
        # `unique` no hash: o mesmo segredo não pode existir duas vezes, e o
        # índice é o que faz o `resolver` casar por hash sem varrer a tabela.
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("prefixo", sa.String(16), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("criado_por", sa.String(200)),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_por", sa.String(200)),
        sa.Column("expira_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_token_automacao_usuario_id", "token_automacao", ["usuario_id"])
    op.create_index("ix_token_automacao_token_hash", "token_automacao", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_token_automacao_token_hash", table_name="token_automacao")
    op.drop_index("ix_token_automacao_usuario_id", table_name="token_automacao")
    op.drop_table("token_automacao")
