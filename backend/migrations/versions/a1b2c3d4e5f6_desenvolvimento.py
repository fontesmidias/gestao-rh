"""Cadastro de Desenvolvimento (Onda B): cursos, certificações e qualificações
do colaborador ao longo do vínculo. Brigadista NÃO é módulo — é uma consulta
sobre estas tabelas (tipo com validade + crítico + cargos aplicáveis).

Tabelas: tipo_desenvolvimento, prazo_validade (sobrescrita por cargo/posto),
registro_desenvolvimento, arquivo_desenvolvimento.

Revision ID: a1b2c3d4e5f6
Revises: d4e5f6a7b8c9
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None

STATUS_REGISTRO = ("pendente", "validado", "recusado", "devolvido")
SENSIBILIDADE = ("comum", "identidade", "saude")


def upgrade() -> None:
    status = postgresql.ENUM(*STATUS_REGISTRO, name="status_registro_desenvolvimento")
    status.create(op.get_bind(), checkfirst=True)
    sensib = postgresql.ENUM(*SENSIBILIDADE, name="sensibilidade_doc")
    sensib.create(op.get_bind(), checkfirst=True)
    # create_type=False: os tipos já foram criados acima; as colunas só os
    # referenciam (senão create_table tentaria criá-los de novo -> DuplicateObject).
    status_col = postgresql.ENUM(*STATUS_REGISTRO,
                                 name="status_registro_desenvolvimento", create_type=False)
    sensib_col = postgresql.ENUM(*SENSIBILIDADE, name="sensibilidade_doc",
                                 create_type=False)

    op.create_table(
        "tipo_desenvolvimento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False, unique=True),
        sa.Column("descricao", sa.Text()),
        sa.Column("exige_validade", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("meses_validade", sa.Integer()),
        sa.Column("critico", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cargos_aplicaveis", sa.JSON()),
        sa.Column("documentos_exigidos", sa.JSON()),
        sa.Column("aviso_dias_antes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tipo_desenvolvimento_nome", "tipo_desenvolvimento", ["nome"])

    op.create_table(
        "prazo_validade",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tipo_desenvolvimento.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("cargo", sa.String(120)),
        sa.Column("posto_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("posto_servico.id", ondelete="CASCADE")),
        sa.Column("meses_validade", sa.Integer(), nullable=False),
    )
    op.create_index("ix_prazo_validade_tipo_id", "prazo_validade", ["tipo_id"])
    op.create_index("ix_prazo_validade_cargo", "prazo_validade", ["cargo"])
    op.create_index("ix_prazo_validade_posto_id", "prazo_validade", ["posto_id"])

    op.create_table(
        "registro_desenvolvimento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False),
        sa.Column("tipo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tipo_desenvolvimento.id"), nullable=False),
        sa.Column("status", status_col, nullable=False, server_default="pendente"),
        sa.Column("titulo", sa.String(200)),
        sa.Column("instituicao", sa.String(200)),
        sa.Column("carga_horaria", sa.String(30)),
        sa.Column("concluido_em", sa.Date()),
        sa.Column("validade_ate", sa.Date()),
        sa.Column("observacao", sa.Text()),
        sa.Column("extraido_ia", sa.JSON()),
        sa.Column("lido_por_ia_em", sa.DateTime(timezone=True)),
        sa.Column("validado_por", sa.String(200)),
        sa.Column("validado_em", sa.DateTime(timezone=True)),
        sa.Column("motivo_recusa", sa.Text()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("enviado_por", sa.String(20), nullable=False,
                  server_default="colaborador"),
    )
    op.create_index("ix_registro_desenvolvimento_candidato_id",
                    "registro_desenvolvimento", ["candidato_id"])
    op.create_index("ix_registro_desenvolvimento_tipo_id",
                    "registro_desenvolvimento", ["tipo_id"])
    op.create_index("ix_registro_desenvolvimento_status",
                    "registro_desenvolvimento", ["status"])
    op.create_index("ix_registro_desenvolvimento_validade_ate",
                    "registro_desenvolvimento", ["validade_ate"])
    op.create_index("ix_registro_desenvolvimento_criado_em",
                    "registro_desenvolvimento", ["criado_em"])

    op.create_table(
        "arquivo_desenvolvimento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("registro_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("registro_desenvolvimento.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("papel", sa.String(40), nullable=False, server_default="outro"),
        sa.Column("sensibilidade", sensib_col, nullable=False, server_default="comum"),
        sa.Column("key", sa.String(300), nullable=False),
        sa.Column("nome_original", sa.String(200)),
        sa.Column("content_type", sa.String(100)),
        sa.Column("tamanho", sa.Integer()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_arquivo_desenvolvimento_registro_id",
                    "arquivo_desenvolvimento", ["registro_id"])


def downgrade() -> None:
    op.drop_table("arquivo_desenvolvimento")
    op.drop_table("registro_desenvolvimento")
    op.drop_table("prazo_validade")
    op.drop_table("tipo_desenvolvimento")
    postgresql.ENUM(name="sensibilidade_doc").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="status_registro_desenvolvimento").drop(
        op.get_bind(), checkfirst=True)
