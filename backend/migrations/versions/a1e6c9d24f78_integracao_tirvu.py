"""Integração "manual" com o Tirvu (leva 2026-07-19): tabelas Empresa e Jornada
(o RH escolhe ou cria), vínculo empresa/jornada/registra-ponto no candidato,
CTPS derivada do CPF (padrão eSocial: número = CPF, série = 0000), endereço
separado em logradouro/número/complemento (coleta nova; o legado fica) e os
campos do laudo PCD (CID, tipo, data, médico/CRM).

Revision ID: a1e6c9d24f78
Revises: d8f2a4c61b93
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a1e6c9d24f78"
down_revision = "d8f2a4c61b93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "empresa",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("razao_social", sa.String(200), nullable=False, unique=True),
        sa.Column("cnpj", sa.String(20), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "jornada",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("descricao", sa.String(300), nullable=False, unique=True),
        sa.Column("posto_servico_id", UUID(as_uuid=True),
                  sa.ForeignKey("posto_servico.id"), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    op.add_column("candidato", sa.Column("empresa_id", UUID(as_uuid=True),
                                         sa.ForeignKey("empresa.id"), nullable=True))
    op.add_column("candidato", sa.Column("jornada_id", UUID(as_uuid=True),
                                         sa.ForeignKey("jornada.id"), nullable=True))
    op.add_column("candidato", sa.Column("registra_ponto", sa.Boolean(), nullable=True))

    op.add_column("documentos_identificacao",
                  sa.Column("ctps_numero", sa.String(11), nullable=True))
    op.add_column("documentos_identificacao",
                  sa.Column("ctps_serie", sa.String(5), nullable=True))

    op.add_column("endereco", sa.Column("logradouro", sa.String(200), nullable=True))
    op.add_column("endereco", sa.Column("numero", sa.String(20), nullable=True))
    op.add_column("endereco", sa.Column("complemento", sa.String(120), nullable=True))

    op.add_column("dados_pessoais", sa.Column("pcd_cid", sa.String(20), nullable=True))
    op.add_column("dados_pessoais", sa.Column("pcd_tipo", sa.String(30), nullable=True))
    op.add_column("dados_pessoais", sa.Column("pcd_data_laudo", sa.Date(), nullable=True))
    op.add_column("dados_pessoais", sa.Column("pcd_medico_crm", sa.String(120), nullable=True))

    # A Green House já nasce cadastrada — é a empregadora de hoje; as demais o
    # RH cria pelo painel.
    op.execute(
        "INSERT INTO empresa (id, razao_social, cnpj, ativa) VALUES "
        "(gen_random_uuid(), 'GREEN HOUSE SERVICOS DE LOCACAO DE MAO DE OBRA LTDA', "
        "NULL, true) ON CONFLICT (razao_social) DO NOTHING"
    )


def downgrade() -> None:
    for col in ("pcd_medico_crm", "pcd_data_laudo", "pcd_tipo", "pcd_cid"):
        op.drop_column("dados_pessoais", col)
    for col in ("complemento", "numero", "logradouro"):
        op.drop_column("endereco", col)
    for col in ("ctps_serie", "ctps_numero"):
        op.drop_column("documentos_identificacao", col)
    for col in ("registra_ponto", "jornada_id", "empresa_id"):
        op.drop_column("candidato", col)
    op.drop_table("jornada")
    op.drop_table("empresa")
