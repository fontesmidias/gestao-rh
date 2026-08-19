"""Comprovante mensal de despesa do creche (competência por criança/mês).

O e-mail de ativação já mandava enviar nota fiscal (creche PJ) ou declaração de
quitação (cuidador PF) todo mês, e não havia onde receber — ver o docstring de
`app/models/creche_competencia.py`.

Sem backfill: não existe dado antigo a migrar (as competências passadas nunca
foram coletadas por aqui). E **nada de INSERT cru** nesta revisão — a lição da
v2.70, onde um `INSERT` que não listava coluna `NOT NULL` sem `server_default`
passou verde em banco vazio e derrubou a API em produção.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b5d9e2a7c134"
down_revision = "a3f7c1e9d5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competencia_creche",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("beneficio_id", UUID(as_uuid=True),
                  sa.ForeignKey("beneficio_creche.id"), nullable=False, index=True),
        sa.Column("crianca_id", UUID(as_uuid=True),
                  sa.ForeignKey("crianca_creche.id"), nullable=False, index=True),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="enviado"),
        sa.Column("tipo_comprovante", sa.String(20)),
        sa.Column("valor_centavos", sa.Integer()),
        sa.Column("valor_informado_texto", sa.String(30)),
        sa.Column("arquivo_pdf_key", sa.String(300)),
        sa.Column("paginas", sa.Integer()),
        sa.Column("enviado_em", sa.DateTime(timezone=True)),
        sa.Column("enviado_por", sa.String(200)),
        sa.Column("analisado_por", sa.String(200)),
        sa.Column("analisado_em", sa.DateTime(timezone=True)),
        sa.Column("motivo_recusa", sa.String(400)),
        sa.Column("anterior_a_vigencia", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        # Um comprovante por criança por mês: dois registros do mesmo mês
        # fariam a soma da folha dobrar sem nada denunciar. O reenvio
        # SUBSTITUI (a rota expurga o anterior), não acrescenta.
        sa.UniqueConstraint("crianca_id", "ano", "mes",
                            name="uq_competencia_crianca_mes"),
    )


def downgrade() -> None:
    op.drop_table("competencia_creche")
