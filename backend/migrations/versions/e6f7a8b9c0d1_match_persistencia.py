"""Persistência do Match de Vagas (v2.00): texto do currículo extraído uma
vez, processamento assíncrono e análise por talento com o MOTIVO.

Corrige o incidente de 2026-07-28 em que nada era guardado e cada clique
refazia as 131 análises, estourando a cota da IA.

ATENÇÃO (armadilha que já mordeu em c4d5e6f7a8b9): usar
`postgresql.ENUM(..., create_type=False)` do DIALETO — o `sa.Enum` genérico
não respeita a flag e o `op.create_table` dispara CREATE TYPE de novo,
colidindo com o `.create()` explícito (DuplicateObject).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

_STATUS_PROC = postgresql.ENUM(
    "na_fila", "processando", "concluido", "concluido_sem_ia", "falhou",
    name="match_status_processamento", create_type=False)
_RESULTADO = postgresql.ENUM(
    "analisado", "sem_curriculo", "curriculo_ilegivel", "ia_indisponivel", "erro",
    name="match_resultado_analise", create_type=False)


def upgrade() -> None:
    _STATUS_PROC.create(op.get_bind(), checkfirst=True)
    _RESULTADO.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "curriculo_texto",
        sa.Column("talento_id", UUID(as_uuid=True),
                  sa.ForeignKey("talento.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("curriculo_key", sa.String(length=300), nullable=True),
        sa.Column("legivel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("motivo_falha", sa.String(length=120), nullable=True),
        sa.Column("caracteres", sa.Integer(), nullable=True),
        sa.Column("extraido_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "match_processamento",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("vaga_id", UUID(as_uuid=True),
                  sa.ForeignKey("vaga.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", _STATUS_PROC, nullable=False, server_default="na_fila"),
        sa.Column("total_talentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analisados_ia", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reaproveitados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sem_curriculo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ilegiveis", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspeitos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observacao", sa.String(length=300), nullable=True),
        sa.Column("solicitado_por", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_match_processamento_vaga_id", "match_processamento", ["vaga_id"])
    op.create_index("ix_match_processamento_status", "match_processamento", ["status"])

    op.create_table(
        "match_analise",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("vaga_id", UUID(as_uuid=True),
                  sa.ForeignKey("vaga.id", ondelete="CASCADE"), nullable=False),
        sa.Column("talento_id", UUID(as_uuid=True),
                  sa.ForeignKey("talento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("processamento_id", UUID(as_uuid=True),
                  sa.ForeignKey("match_processamento.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resultado", _RESULTADO, nullable=False),
        sa.Column("nota", sa.Integer(), nullable=True),
        sa.Column("atende_obrigatorios", sa.Boolean(), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("bate_filtro", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("curriculo_suspeito", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provedor", sa.String(length=30), nullable=True),
        sa.Column("detalhe_falha", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("vaga_id", "talento_id", name="uq_analise_vaga_talento"),
    )
    op.create_index("ix_match_analise_vaga_id", "match_analise", ["vaga_id"])
    op.create_index("ix_match_analise_talento_id", "match_analise", ["talento_id"])
    op.create_index("ix_match_analise_resultado", "match_analise", ["resultado"])


def downgrade() -> None:
    op.drop_index("ix_match_analise_resultado", table_name="match_analise")
    op.drop_index("ix_match_analise_talento_id", table_name="match_analise")
    op.drop_index("ix_match_analise_vaga_id", table_name="match_analise")
    op.drop_table("match_analise")
    op.drop_index("ix_match_processamento_status", table_name="match_processamento")
    op.drop_index("ix_match_processamento_vaga_id", table_name="match_processamento")
    op.drop_table("match_processamento")
    op.drop_table("curriculo_texto")
    postgresql.ENUM(name="match_resultado_analise").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="match_status_processamento").drop(op.get_bind(), checkfirst=True)
