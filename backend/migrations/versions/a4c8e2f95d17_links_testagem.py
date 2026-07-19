"""Links de testagem: aplicação avulsa dos testes com resultado ao participante.

Revision ID: a4c8e2f95d17
Revises: e9b4c6d83f15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "a4c8e2f95d17"
down_revision = "e9b4c6d83f15"
branch_labels = None
depends_on = None

# Tipos criados na migration dos testes do candidato — aqui só referenciamos
# (create_type=False, senão DuplicateObject).
tipo_teste = postgresql.ENUM("disc", "situacional", name="tipo_teste", create_type=False)
status_teste = postgresql.ENUM("pendente", "em_andamento", "concluido", "expirado",
                               name="status_teste", create_type=False)


def upgrade() -> None:
    op.create_table(
        "link_testagem",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("criado_por", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "participante_testagem",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("link_id", UUID(as_uuid=True),
                  sa.ForeignKey("link_testagem.id"), nullable=False, index=True),
        sa.Column("nome", sa.String(length=200), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "teste_testagem",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("participante_id", UUID(as_uuid=True),
                  sa.ForeignKey("participante_testagem.id"), nullable=False, index=True),
        sa.Column("tipo", tipo_teste, nullable=False),
        sa.Column("status", status_teste, nullable=False,
                  server_default=sa.text("'pendente'")),
        sa.Column("iniciado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prazo_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respostas", sa.JSON(), nullable=True),
        sa.Column("resultado", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("teste_testagem")
    op.drop_table("participante_testagem")
    op.drop_table("link_testagem")
