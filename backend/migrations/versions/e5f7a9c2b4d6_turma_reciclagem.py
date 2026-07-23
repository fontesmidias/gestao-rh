"""Turmas de reciclagem e solicitação de matrícula à entidade formadora
(Multicursos). Turma é ENTIDADE para permitir o "clique único": escolhida a
turma, o e-mail se monta para todos os marcados no dash.

A solicitação guarda o texto FINAL enviado (o RH edita antes de mandar) — é a
prova do que foi pedido.

Revision ID: e5f7a9c2b4d6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ATENÇÃO ao escolher revision id nova: "b2c3d4e5f6a7" (o id óbvio na sequência
# deste arquivo) JÁ EXISTE em `b2c3d4e5f6a7_status_importado.py` e reusá-lo
# fecha um CICLO no grafo do Alembic ("Cycle is detected in revisions"), que
# derruba o upgrade inteiro — inclusive o do entrypoint em produção.
revision = "e5f7a9c2b4d6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "turma_reciclagem",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tipo_desenvolvimento.id")),
        sa.Column("entidade", sa.String(200), nullable=False,
                  server_default="Multicursos"),
        sa.Column("inicio_em", sa.Date(), nullable=False),
        sa.Column("periodo", sa.String(20), nullable=False, server_default="noturno"),
        sa.Column("observacao", sa.Text()),
        sa.Column("email_destino", sa.String(200)),
        sa.Column("encerrada", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_turma_reciclagem_tipo_id", "turma_reciclagem", ["tipo_id"])
    op.create_index("ix_turma_reciclagem_inicio_em", "turma_reciclagem", ["inicio_em"])

    op.create_table(
        "solicitacao_matricula",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("turma_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("turma_reciclagem.id")),
        sa.Column("turma_inicio_em", sa.Date()),
        sa.Column("turma_periodo", sa.String(20)),
        sa.Column("destinatarios", sa.JSON()),
        sa.Column("assunto", sa.String(300)),
        sa.Column("corpo", sa.Text()),
        sa.Column("colaboradores", sa.JSON()),
        sa.Column("enviado_em", sa.DateTime(timezone=True)),
        sa.Column("enviado_por", sa.String(200)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_solicitacao_matricula_turma_id",
                    "solicitacao_matricula", ["turma_id"])
    op.create_index("ix_solicitacao_matricula_criado_em",
                    "solicitacao_matricula", ["criado_em"])

    # O aviso de vencimento passa a 90 dias por padrão (decisão do Bruno,
    # 2026-07-22): é o tempo real de juntar documento, marcar exame e a clínica
    # abrir turma. Continua editável por tipo no painel.
    op.alter_column("tipo_desenvolvimento", "aviso_dias_antes",
                    server_default="90", existing_type=sa.Integer())
    op.execute("UPDATE tipo_desenvolvimento SET aviso_dias_antes = 90 "
               "WHERE aviso_dias_antes = 60")


def downgrade() -> None:
    op.alter_column("tipo_desenvolvimento", "aviso_dias_antes",
                    server_default="60", existing_type=sa.Integer())
    op.drop_table("solicitacao_matricula")
    op.drop_table("turma_reciclagem")
