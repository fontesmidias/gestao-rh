"""Modelos assináveis + papéis de assinatura + telemetria na testagem.

- assinatura: agora aceita documento de modelo do RH (modelo_id + snapshot de
  título/corpo) além dos documentos fixos do enum; ganha o papel do signatário.
- modelo_documento: flags de envio por e-mail / exigência de assinatura e o
  papel com que o colaborador assina.
- papel_assinatura: CRUD dos papéis (Contratado(a), Contratante, Testemunha,
  Validador(a)) que compõem o manifesto.
- teste_testagem: coluna de eventos (telemetria de comportamento).

Revision ID: b6d1f4a82c39
Revises: a4c8e2f95d17
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

# tipo já existente — só referência (create_type=False, senão DuplicateObject)
documento_assinavel = postgresql.ENUM(name="documento_assinavel", create_type=False)

revision = "b6d1f4a82c39"
down_revision = "a4c8e2f95d17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # assinatura de modelos do RH
    op.alter_column("assinatura", "documento", nullable=True,
                    existing_type=documento_assinavel)
    op.add_column("assinatura", sa.Column(
        "modelo_id", UUID(as_uuid=True),
        sa.ForeignKey("modelo_documento.id"), nullable=True))
    op.add_column("assinatura", sa.Column("titulo_doc", sa.String(length=200), nullable=True))
    op.add_column("assinatura", sa.Column("corpo_doc", sa.Text(), nullable=True))
    op.add_column("assinatura", sa.Column("papel", sa.String(length=60), nullable=True))

    # comportamento do modelo ao gerar/enviar
    op.add_column("modelo_documento", sa.Column(
        "enviar_por_email", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("modelo_documento", sa.Column(
        "exige_assinatura", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("modelo_documento", sa.Column(
        "papel_assinatura", sa.String(length=60), nullable=True))

    # papéis de assinatura (com seed dos 4 padrões do mercado)
    papel = op.create_table(
        "papel_assinatura",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(length=60), nullable=False, unique=True),
        sa.Column("descricao", sa.String(length=300), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.bulk_insert(papel, [
        {"id": uuid.uuid4(), "nome": "Contratado(a)", "ordem": 1,
         "descricao": "Quem é admitido/contratado — o colaborador ou candidato."},
        {"id": uuid.uuid4(), "nome": "Contratante", "ordem": 2,
         "descricao": "Representante da empresa que contrata."},
        {"id": uuid.uuid4(), "nome": "Testemunha", "ordem": 3,
         "descricao": "Terceiro que atesta que a assinatura ocorreu."},
        {"id": uuid.uuid4(), "nome": "Validador(a)", "ordem": 4,
         "descricao": "Quem confere e valida o documento (ex.: RH)."},
    ])

    # telemetria na testagem avulsa
    op.add_column("teste_testagem", sa.Column("eventos", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("teste_testagem", "eventos")
    op.drop_table("papel_assinatura")
    op.drop_column("modelo_documento", "papel_assinatura")
    op.drop_column("modelo_documento", "exige_assinatura")
    op.drop_column("modelo_documento", "enviar_por_email")
    op.drop_column("assinatura", "papel")
    op.drop_column("assinatura", "corpo_doc")
    op.drop_column("assinatura", "titulo_doc")
    op.drop_column("assinatura", "modelo_id")
    op.alter_column("assinatura", "documento", nullable=False,
                    existing_type=documento_assinavel)
