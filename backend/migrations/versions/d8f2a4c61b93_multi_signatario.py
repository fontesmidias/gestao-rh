"""Multi-signatário: solicitação + etapas de assinatura, roteiro-padrão do
modelo, autorização da equipe, e marca da assinatura de roteiro do candidato.

Revision ID: d8f2a4c61b93
Revises: c7e3a1f95d82
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

revision = "d8f2a4c61b93"
down_revision = "c7e3a1f95d82"
branch_labels = None
depends_on = None

# documento_assinavel JÁ existe (da Assinatura) — só referência
documento_assinavel = postgresql.ENUM(name="documento_assinavel", create_type=False)
status_solicitacao = postgresql.ENUM(
    "rascunho", "aguardando", "concluida", "pendente_rh", "cancelada", "expirada",
    name="status_solicitacao")
tipo_signatario = postgresql.ENUM(
    "candidato", "usuario_rh", "externo", name="tipo_signatario")


def upgrade() -> None:
    bind = op.get_bind()
    status_solicitacao.create(bind, checkfirst=True)
    tipo_signatario.create(bind, checkfirst=True)
    ss = postgresql.ENUM(name="status_solicitacao", create_type=False)
    ts = postgresql.ENUM(name="tipo_signatario", create_type=False)

    op.add_column("assinatura", sa.Column(
        "solicitacao_etapa_id", sa.String(length=36), nullable=True))

    op.create_table(
        "solicitacao_assinatura",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False, index=True),
        sa.Column("documento", documento_assinavel, nullable=True),
        sa.Column("modelo_id", UUID(as_uuid=True),
                  sa.ForeignKey("modelo_documento.id"), nullable=True),
        sa.Column("titulo_doc", sa.String(length=200), nullable=True),
        sa.Column("corpo_doc", sa.Text(), nullable=True),
        sa.Column("status", ss, nullable=False, server_default=sa.text("'rascunho'")),
        sa.Column("etapa_atual_ordem", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("pdf_final_key", sa.String(length=300), nullable=True),
        sa.Column("hash_final_sha256", sa.String(length=64), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelada_motivo", sa.String(length=300), nullable=True),
        sa.Column("criada_por", sa.String(length=120), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "etapa_assinatura",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("solicitacao_id", UUID(as_uuid=True),
                  sa.ForeignKey("solicitacao_assinatura.id"), nullable=False, index=True),
        sa.Column("papel", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("tipo_signatario", ts, nullable=False),
        sa.Column("assinatura_id", UUID(as_uuid=True),
                  sa.ForeignKey("assinatura.id"), nullable=True),
        sa.Column("usuario_rh_id", UUID(as_uuid=True),
                  sa.ForeignKey("usuario_rh.id"), nullable=True),
        sa.Column("externo_nome", sa.String(length=120), nullable=True),
        sa.Column("externo_email", sa.String(length=180), nullable=True),
        sa.Column("externo_cpf", sa.String(length=11), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True, index=True),
        sa.Column("otp_hash", sa.String(length=64), nullable=True),
        sa.Column("otp_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_tentativas", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("otp_validado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assinado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assinante_nome", sa.String(length=200), nullable=True),
        sa.Column("assinante_cpf", sa.String(length=20), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_key", sa.String(length=300), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("prova_metodo", sa.String(length=60), nullable=True),
        sa.Column("recusada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recusada_motivo", sa.String(length=300), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "modelo_etapa_padrao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("modelo_id", UUID(as_uuid=True),
                  sa.ForeignKey("modelo_documento.id"), nullable=False, index=True),
        sa.Column("papel", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("tipo_sugerido", ts, nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "autorizacao_equipe",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("modelo_id", UUID(as_uuid=True),
                  sa.ForeignKey("modelo_documento.id"), nullable=False, index=True),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("cargo", sa.String(length=120), nullable=True),
        sa.Column("cpf", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("papel", sa.String(length=60), nullable=False, server_default=sa.text("'Contratante'")),
        sa.Column("autorizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("validade_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_hash", sa.String(length=64), nullable=True),
        sa.Column("otp_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por", sa.String(length=120), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("autorizacao_equipe")
    op.drop_table("modelo_etapa_padrao")
    op.drop_table("etapa_assinatura")
    op.drop_table("solicitacao_assinatura")
    op.drop_column("assinatura", "solicitacao_etapa_id")
    # NÃO dropar documento_assinavel (é da Assinatura legada) — só os enums novos.
    bind = op.get_bind()
    postgresql.ENUM(name="tipo_signatario").drop(bind, checkfirst=True)
    postgresql.ENUM(name="status_solicitacao").drop(bind, checkfirst=True)
