"""Benefício Reembolso-Creche: adesão do colaborador (BeneficioCreche),
crianças (CriancaCreche) e sessão do link público (AcessoCreche).

Revision ID: a1c8e4f70b23
Revises: f9a3b7e21c46
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1c8e4f70b23"
down_revision = "f9a3b7e21c46"
branch_labels = None
depends_on = None

STATUS = ("levantamento", "em_analise", "aguardando_repactuacao", "ativo",
          "suspenso", "encerrado", "indeferido")


def upgrade() -> None:
    status_beneficio = postgresql.ENUM(*STATUS, name="status_beneficio")
    status_beneficio.create(op.get_bind(), checkfirst=True)
    # create_type=False: o tipo já foi criado acima; a coluna só o referencia
    # (senão create_table tentaria criá-lo de novo -> DuplicateObject).
    status_col = postgresql.ENUM(*STATUS, name="status_beneficio", create_type=False)

    op.create_table(
        "beneficio_creche",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False, unique=True),
        sa.Column("status", status_col, nullable=False, server_default="levantamento"),
        sa.Column("email_confirmado", sa.String(200)),
        sa.Column("email_confirmado_em", sa.DateTime(timezone=True)),
        sa.Column("telefone", sa.String(20)),
        sa.Column("dados_conferidos_em", sa.DateTime(timezone=True)),
        sa.Column("requerimento_assinado_em", sa.DateTime(timezone=True)),
        sa.Column("enviado_em", sa.DateTime(timezone=True)),
        sa.Column("revisado_por", sa.String(200)),
        sa.Column("revisado_em", sa.DateTime(timezone=True)),
        sa.Column("motivo_indeferimento", sa.String(400)),
        sa.Column("ativado_em", sa.DateTime(timezone=True)),
        sa.Column("dossie_pdf_key", sa.String(300)),
        sa.Column("dossie_gerado_em", sa.DateTime(timezone=True)),
        sa.Column("dia_entrega_mensal", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("valor_reembolso", sa.String(30)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_beneficio_creche_candidato_id", "beneficio_creche", ["candidato_id"])

    op.create_table(
        "crianca_creche",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("beneficio_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("beneficio_creche.id"), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("data_nascimento", sa.String(10), nullable=False),
        sa.Column("parentesco", sa.String(30), nullable=False),
        sa.Column("certidao_key", sa.String(300)),
        sa.Column("guarda_key", sa.String(300)),
        sa.Column("tipo_comprovante", sa.String(20)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_crianca_creche_beneficio_id", "crianca_creche", ["beneficio_id"])

    op.create_table(
        "acesso_creche",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("beneficio_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("beneficio_creche.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("codigo_hash", sa.String(64)),
        sa.Column("codigo_expira_em", sa.DateTime(timezone=True)),
        sa.Column("confirmado_em", sa.DateTime(timezone=True)),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_acesso_creche_beneficio_id", "acesso_creche", ["beneficio_id"])
    op.create_index("ix_acesso_creche_token_hash", "acesso_creche", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("acesso_creche")
    op.drop_table("crianca_creche")
    op.drop_table("beneficio_creche")
    postgresql.ENUM(name="status_beneficio").drop(op.get_bind(), checkfirst=True)
