"""Colaborador como entidade de 1ª classe (vínculo, importação do Tirvu) +
elegibilidade de reembolso-creche por posto.

- status_candidato ganha 'ativo' e 'desligado' (o candidato aprovado vira
  colaborador no mesmo registro; importados do Tirvu já entram assim).
- candidato ganha campos de vínculo: cpf, matrícula, nascimento, situação,
  datas de admissão/desligamento, origem e dados_tirvu (colunas dinâmicas).
- posto_servico ganha da_direito_creche + valor_reembolso_creche (o direito
  ao benefício é por posto/contrato, com valor que varia por repactuação).

Revision ID: e7c4a2f91d38
Revises: d5a1b8f34c92
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op

revision = "e7c4a2f91d38"
down_revision = "d5a1b8f34c92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE status_candidato ADD VALUE IF NOT EXISTS 'ativo'")
        op.execute("ALTER TYPE status_candidato ADD VALUE IF NOT EXISTS 'desligado'")

    op.add_column("candidato", sa.Column("cpf", sa.String(length=14), nullable=True))
    op.add_column("candidato", sa.Column("matricula", sa.String(length=30), nullable=True))
    op.add_column("candidato", sa.Column("data_nascimento", sa.String(length=10), nullable=True))
    op.add_column("candidato", sa.Column("situacao", sa.String(length=20), nullable=True))
    op.add_column("candidato", sa.Column("data_admissao", sa.String(length=10), nullable=True))
    op.add_column("candidato", sa.Column("data_desligamento", sa.String(length=10), nullable=True))
    op.add_column("candidato",
                  sa.Column("origem", sa.String(length=20), nullable=False, server_default="admissao"))
    op.add_column("candidato",
                  sa.Column("dados_tirvu", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_candidato_cpf", "candidato", ["cpf"])
    op.create_index("ix_candidato_matricula", "candidato", ["matricula"])

    op.add_column("posto_servico",
                  sa.Column("da_direito_creche", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column("posto_servico",
                  sa.Column("valor_reembolso_creche", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("posto_servico", "valor_reembolso_creche")
    op.drop_column("posto_servico", "da_direito_creche")
    op.drop_index("ix_candidato_matricula", table_name="candidato")
    op.drop_index("ix_candidato_cpf", table_name="candidato")
    op.drop_column("candidato", "dados_tirvu")
    op.drop_column("candidato", "origem")
    op.drop_column("candidato", "data_desligamento")
    op.drop_column("candidato", "data_admissao")
    op.drop_column("candidato", "situacao")
    op.drop_column("candidato", "data_nascimento")
    op.drop_column("candidato", "matricula")
    op.drop_column("candidato", "cpf")
    # Os valores de enum 'ativo'/'desligado' permanecem: Postgres não remove
    # valores de ENUM sem recriar o tipo; deixá-los é inócuo.
