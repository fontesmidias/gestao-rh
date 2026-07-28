"""Minutário de mensagens (v1.98, feedback 2026-07-27): modelos de mensagem
para WhatsApp/e-mail com campos estruturados, gerados por IA (Groq) e
aprovados pelo RH antes de enviar.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

_MEIO = postgresql.ENUM("whatsapp", "email", "outro", name="minutario_meio", create_type=False)


def upgrade() -> None:
    _MEIO.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "minutario_modelo",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("meio", _MEIO, nullable=False, server_default="whatsapp"),
        sa.Column("corpo_base", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "minutario_modelo_tag",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("modelo_id", UUID(as_uuid=True),
                  sa.ForeignKey("minutario_modelo.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", UUID(as_uuid=True),
                  sa.ForeignKey("crm_tag.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_minutario_modelo_tag_modelo_id", "minutario_modelo_tag", ["modelo_id"])
    op.create_index("ix_minutario_modelo_tag_tag_id", "minutario_modelo_tag", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_minutario_modelo_tag_tag_id", table_name="minutario_modelo_tag")
    op.drop_index("ix_minutario_modelo_tag_modelo_id", table_name="minutario_modelo_tag")
    op.drop_table("minutario_modelo_tag")
    op.drop_table("minutario_modelo")
    postgresql.ENUM(name="minutario_meio").drop(op.get_bind(), checkfirst=True)
