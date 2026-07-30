"""Telemetria de uso (v2.24): o que acontece no aparelho da pessoa.

A telemetria HTTP que já existia só registrava o lado do servidor e ia para o
log do container — por isso o `TypeError` que travou dois candidatos em
2026-07-29 não deixou rastro nenhum. Esta tabela guarda erro de JS, fricção,
jornada e desempenho, ligados à pessoa, com retenção configurável.

`tipo` e `origem` são VARCHAR e não enum do Postgres de propósito: são
vocabulários que vão crescer (evento novo a cada tela nova), e cada valor novo
num enum exigiria migration com `ALTER TYPE` — a armadilha registrada no
CLAUDE.md. A validação fica no Python (`TipoTelemetria`/`OrigemTelemetria`).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evento_telemetria",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False, index=True),
        sa.Column("origem", sa.String(20), nullable=False, index=True),
        sa.Column("candidato_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("talento_id", UUID(as_uuid=True),
                  sa.ForeignKey("talento.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("usuario_rh", sa.String(200), nullable=True),
        sa.Column("sessao", sa.String(40), nullable=True, index=True),
        sa.Column("evento", sa.String(60), nullable=False, index=True),
        sa.Column("pagina", sa.String(120), nullable=True, index=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("detalhe", JSONB, nullable=True),
        sa.Column("versao", sa.String(40), nullable=True),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("ip_prefixo", sa.String(20), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
    )
    # Índices compostos: as três consultas que a tela do RH realmente faz.
    op.create_index("ix_telemetria_tipo_data", "evento_telemetria",
                    ["tipo", "criado_em"])
    op.create_index("ix_telemetria_candidato_data", "evento_telemetria",
                    ["candidato_id", "criado_em"])
    op.create_index("ix_telemetria_talento_data", "evento_telemetria",
                    ["talento_id", "criado_em"])


def downgrade() -> None:
    op.drop_index("ix_telemetria_talento_data", table_name="evento_telemetria")
    op.drop_index("ix_telemetria_candidato_data", table_name="evento_telemetria")
    op.drop_index("ix_telemetria_tipo_data", table_name="evento_telemetria")
    op.drop_table("evento_telemetria")
