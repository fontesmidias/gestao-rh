"""As três tabelas do provedor OAuth do MCP remoto.

Existem para que conectar o assistente ao portal seja o que já é em qualquer
outra plataforma: clicar, fazer login, autorizar. Hoje é instalar Python, abrir
o terminal e editar um JSON — e mesmo um instalador de duplo clique continuaria
pedindo que cada pessoa criasse e colasse uma credencial, que é o passo que o
padrão de mercado não tem.

Molde: `token_automacao` (v2.94) — segredo só como sha256, revogar MARCA e não
apaga, e a property `valido` concentrando a decisão.

⚠️ **Nenhum enum aqui, de propósito.** `origem` e `revogado_motivo` são
`String`: são poucos valores que ainda podem crescer, e valor novo de enum no
Postgres custa a dança das DUAS revisões separadas (`ALTER TYPE ... ADD VALUE`
não pode ser usado na mesma transação que o cria). String com comentário é mais
barato e não tem a armadilha.

Revision ID: c7f2a9e4b830
Revises: d4e8b2f6a9c1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c7f2a9e4b830"
down_revision = "d4e8b2f6a9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_cliente_oauth",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # 500 e não 64: no CIMD o próprio `client_id` é a URL do documento de
        # metadados. Coluna dimensionada para a porta mais LARGA (v2.89.1).
        sa.Column("client_id", sa.String(500), nullable=False, unique=True),
        sa.Column("client_name", sa.String(200), nullable=False),
        sa.Column("redirect_uris", JSONB, nullable=False, server_default="[]"),
        sa.Column("origem", sa.String(20), nullable=False, server_default="dcr"),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("criado_por_ip", sa.String(45)),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_por", sa.String(200)),
    )
    op.create_index("ix_mcp_cliente_oauth_client_id", "mcp_cliente_oauth", ["client_id"])

    op.create_table(
        "mcp_codigo_autorizacao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("codigo_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("cliente_id", UUID(as_uuid=True),
                  sa.ForeignKey("mcp_cliente_oauth.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", UUID(as_uuid=True),
                  sa.ForeignKey("usuario_rh.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("escopo", sa.String(500), nullable=False, server_default=""),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        sa.Column("concessao_id", UUID(as_uuid=True)),
    )
    op.create_index("ix_mcp_codigo_autorizacao_codigo_hash",
                    "mcp_codigo_autorizacao", ["codigo_hash"])
    op.create_index("ix_mcp_codigo_autorizacao_cliente_id",
                    "mcp_codigo_autorizacao", ["cliente_id"])
    op.create_index("ix_mcp_codigo_autorizacao_usuario_id",
                    "mcp_codigo_autorizacao", ["usuario_id"])

    op.create_table(
        "mcp_concessao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cliente_id", UUID(as_uuid=True),
                  sa.ForeignKey("mcp_cliente_oauth.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario_id", UUID(as_uuid=True),
                  sa.ForeignKey("usuario_rh.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False, unique=True),
        # ⚠️ É esta coluna que detecta ROUBO: um refresh já rotacionado sendo
        # reapresentado significa que alguém tem uma cópia, e a resposta é
        # revogar a concessão INTEIRA. Sem ela, o reuso seria indistinguível de
        # "não existe" e a concessão legítima seguiria viva com o ladrão.
        sa.Column("refresh_hash_anterior", sa.String(64)),
        sa.Column("refresh_prefixo", sa.String(16), nullable=False),
        sa.Column("resource", sa.String(500), nullable=False),
        sa.Column("escopo", sa.String(500), nullable=False, server_default=""),
        sa.Column("papel_concedido", sa.String(50), nullable=False),
        sa.Column("papel_do_usuario", sa.String(50), nullable=False),
        sa.Column("geracao", sa.Integer, nullable=False, server_default="1"),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True)),
        sa.Column("expira_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_em", sa.DateTime(timezone=True)),
        sa.Column("revogado_por", sa.String(200)),
        sa.Column("revogado_motivo", sa.String(100)),
    )
    op.create_index("ix_mcp_concessao_refresh_hash", "mcp_concessao", ["refresh_hash"])
    op.create_index("ix_mcp_concessao_refresh_hash_anterior",
                    "mcp_concessao", ["refresh_hash_anterior"])
    op.create_index("ix_mcp_concessao_cliente_id", "mcp_concessao", ["cliente_id"])
    op.create_index("ix_mcp_concessao_usuario_id", "mcp_concessao", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_concessao_usuario_id", table_name="mcp_concessao")
    op.drop_index("ix_mcp_concessao_cliente_id", table_name="mcp_concessao")
    op.drop_index("ix_mcp_concessao_refresh_hash_anterior", table_name="mcp_concessao")
    op.drop_index("ix_mcp_concessao_refresh_hash", table_name="mcp_concessao")
    op.drop_table("mcp_concessao")

    op.drop_index("ix_mcp_codigo_autorizacao_usuario_id", table_name="mcp_codigo_autorizacao")
    op.drop_index("ix_mcp_codigo_autorizacao_cliente_id", table_name="mcp_codigo_autorizacao")
    op.drop_index("ix_mcp_codigo_autorizacao_codigo_hash", table_name="mcp_codigo_autorizacao")
    op.drop_table("mcp_codigo_autorizacao")

    op.drop_index("ix_mcp_cliente_oauth_client_id", table_name="mcp_cliente_oauth")
    op.drop_table("mcp_cliente_oauth")
