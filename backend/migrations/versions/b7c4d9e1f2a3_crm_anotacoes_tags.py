"""Mini-CRM: anotações e tags que acompanham a pessoa (talento+candidato).

Três tabelas: crm_tag (catálogo), crm_pessoa_tag (vínculo N:N com 2 FKs
opcionais), crm_anotacao (nota + autor snapshot + anexo opcional). Sem enum novo.

Revision ID: b7c4d9e1f2a3
Revises: e8f3a1c9d2b7
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b7c4d9e1f2a3"
down_revision = "e8f3a1c9d2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_tag",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(60), nullable=False),
        sa.Column("cor", sa.String(9), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_tag_nome", "crm_tag", ["nome"], unique=True)

    op.create_table(
        "crm_pessoa_tag",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("crm_tag.id", ondelete="CASCADE"), nullable=False),
        sa.Column("talento_id", UUID(as_uuid=True), sa.ForeignKey("talento.id", ondelete="CASCADE"), nullable=True),
        sa.Column("candidato_id", UUID(as_uuid=True), sa.ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True),
        sa.Column("aplicado_por", sa.String(200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tag_id", "talento_id", name="uq_tag_talento"),
        sa.UniqueConstraint("tag_id", "candidato_id", name="uq_tag_candidato"),
    )
    op.create_index("ix_crm_pessoa_tag_tag_id", "crm_pessoa_tag", ["tag_id"])
    op.create_index("ix_crm_pessoa_tag_talento_id", "crm_pessoa_tag", ["talento_id"])
    op.create_index("ix_crm_pessoa_tag_candidato_id", "crm_pessoa_tag", ["candidato_id"])

    op.create_table(
        "crm_anotacao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("talento_id", UUID(as_uuid=True), sa.ForeignKey("talento.id", ondelete="CASCADE"), nullable=True),
        sa.Column("candidato_id", UUID(as_uuid=True), sa.ForeignKey("candidato.id", ondelete="CASCADE"), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("autor_id", UUID(as_uuid=True), sa.ForeignKey("usuario_rh.id"), nullable=True),
        sa.Column("autor_nome", sa.String(200), nullable=False),
        sa.Column("anexo_key", sa.String(300), nullable=True),
        sa.Column("anexo_nome", sa.String(200), nullable=True),
        sa.Column("anexo_tipo", sa.String(100), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_crm_anotacao_talento_id", "crm_anotacao", ["talento_id"])
    op.create_index("ix_crm_anotacao_candidato_id", "crm_anotacao", ["candidato_id"])


def downgrade() -> None:
    op.drop_table("crm_anotacao")
    op.drop_table("crm_pessoa_tag")
    op.drop_index("ix_crm_tag_nome", table_name="crm_tag")
    op.drop_table("crm_tag")
