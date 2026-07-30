"""Alertas de telemetria (v2.25): o sistema avisa em vez de esperar a pergunta.

A telemetria da v2.24 é passiva — alguém precisa abrir a aba. Estas tabelas
guardam as REGRAS configuradas pelo RH (quatro tipos: erro novo, volume de
erro, pico de fricção, lentidão) e a memória do que já foi avisado, que sustenta
o dedup e a janela de silêncio.

`tipo` é VARCHAR e não enum do Postgres: cenário novo não pode exigir
`ALTER TYPE` (armadilha registrada no CLAUDE.md). Validação no Python.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regra_alerta",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False, index=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limiar", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("janela_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("silencio_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("origem", sa.String(20), nullable=True),
        sa.Column("pagina", sa.String(120), nullable=True),
        sa.Column("evento", sa.String(60), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "alerta_enviado",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("regra_id", UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("tipo", sa.String(20), nullable=False, index=True),
        sa.Column("assinatura", sa.String(300), nullable=False, index=True),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("ocorrencias", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("destinatarios", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_alerta_assinatura_data", "alerta_enviado",
                    ["assinatura", "criado_em"])

    # Regras padrão: o sistema já nasce vigiando o que causou o incidente de
    # 2026-07-29. Sem isto, o recurso existiria mas ficaria desligado até
    # alguém configurar — e ninguém configura o que ainda não doeu.
    op.execute("""
        INSERT INTO regra_alerta (id, tipo, nome, ativa, limiar, janela_min,
                                  silencio_min, origem, criado_em)
        VALUES
        (gen_random_uuid(), 'erro_novo',
         'Erro novo na tela de alguém', true, 1, 60, 60, NULL, now()),
        (gen_random_uuid(), 'erro_volume',
         'Erro conhecido disparou de volume', true, 20, 60, 120, NULL, now()),
        (gen_random_uuid(), 'friccao_pico',
         'Muita gente travando no mesmo ponto', true, 10, 60, 120, NULL, now()),
        (gen_random_uuid(), 'lentidao',
         'Página passou de 8 segundos', true, 8000, 60, 180, NULL, now())
    """)


def downgrade() -> None:
    op.drop_index("ix_alerta_assinatura_data", table_name="alerta_enviado")
    op.drop_table("alerta_enviado")
    op.drop_table("regra_alerta")
