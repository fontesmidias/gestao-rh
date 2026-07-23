"""Gestão de Desempenho (Onda C): fatos observados, ciclos e o formulário da
cartilha (11 seções).

Os Fatos Observados rodam SOZINHOS antes do formulário existir — é o antídoto
do efeito de recência, e por isso a tabela nasce junto mas independente.

Revision ID: c7d2e8f4a916
Revises: e5f7a9c2b4d6
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Conferido que o id é único (`grep -rn 'revision = ' migrations/versions/`):
# reusar um existente fecha um CICLO no grafo do Alembic e derruba o upgrade
# inteiro, inclusive o do entrypoint em produção.
revision = "c7d2e8f4a916"
down_revision = "e5f7a9c2b4d6"
branch_labels = None
depends_on = None

TIPO_FATO = ("positivo", "negativo", "neutro")
OCASIAO = ("experiencia_30", "experiencia_45", "experiencia_60", "experiencia_90",
           "intermitente", "periodica", "feedback_pontual", "outro")
RELACAO = ("vertical", "horizontal", "autoavaliacao")
STATUS = ("rascunho", "preenchida", "feedback_dado", "manifestada",
          "homologada", "cancelada")


def upgrade() -> None:
    for nome, valores in (("tipo_fato_observado", TIPO_FATO),
                          ("ocasiao_avaliacao", OCASIAO),
                          ("relacao_avaliador", RELACAO),
                          ("status_avaliacao", STATUS)):
        postgresql.ENUM(*valores, name=nome).create(op.get_bind(), checkfirst=True)

    # create_type=False: os tipos já existem; as colunas só os referenciam
    tipo_fato = postgresql.ENUM(*TIPO_FATO, name="tipo_fato_observado",
                                create_type=False)
    ocasiao = postgresql.ENUM(*OCASIAO, name="ocasiao_avaliacao", create_type=False)
    relacao = postgresql.ENUM(*RELACAO, name="relacao_avaliador", create_type=False)
    status = postgresql.ENUM(*STATUS, name="status_avaliacao", create_type=False)

    op.create_table(
        "ciclo_avaliacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("inicio_em", sa.Date(), nullable=False),
        sa.Column("fim_em", sa.Date(), nullable=False),
        sa.Column("postos", sa.JSON()),
        sa.Column("candidatos", sa.JSON()),
        sa.Column("encerrado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "avaliacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ciclo_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ciclo_avaliacao.id")),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False),
        sa.Column("avaliador", sa.String(200), nullable=False),
        sa.Column("relacao", relacao, nullable=False, server_default="vertical"),
        sa.Column("ocasiao", ocasiao, nullable=False, server_default="periodica"),
        sa.Column("status", status, nullable=False, server_default="rascunho"),
        sa.Column("periodo_inicio", sa.Date()),
        sa.Column("periodo_fim", sa.Date()),
        sa.Column("convocacao_em", sa.Date()),
        sa.Column("ocasiao_outro", sa.String(120)),
        sa.Column("indicadores", sa.JSON()),
        sa.Column("competencias", sa.JSON()),
        sa.Column("pontos_fortes", sa.Text()),
        sa.Column("pontos_desenvolver", sa.Text()),
        sa.Column("pdi", sa.JSON()),
        sa.Column("recomendacao", sa.String(40)),
        sa.Column("recomendacao_data", sa.Date()),
        sa.Column("justificativa", sa.Text()),
        sa.Column("postura", sa.String(20)),
        sa.Column("postura_observacao", sa.Text()),
        sa.Column("feedback_em", sa.Date()),
        sa.Column("manifestacao", sa.Text()),
        sa.Column("manifestacao_em", sa.DateTime(timezone=True)),
        sa.Column("conclusao_aplicador", sa.Text()),
        sa.Column("homologado_por", sa.String(200)),
        sa.Column("homologado_em", sa.DateTime(timezone=True)),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_avaliacao_candidato_id", "avaliacao", ["candidato_id"])
    op.create_index("ix_avaliacao_avaliador", "avaliacao", ["avaliador"])
    op.create_index("ix_avaliacao_ciclo_id", "avaliacao", ["ciclo_id"])
    op.create_index("ix_avaliacao_status", "avaliacao", ["status"])
    op.create_index("ix_avaliacao_criado_em", "avaliacao", ["criado_em"])

    op.create_table(
        "fato_observado",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidato_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("candidato.id"), nullable=False),
        sa.Column("autor", sa.String(200), nullable=False),
        sa.Column("tipo", tipo_fato, nullable=False, server_default="positivo"),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("impacto", sa.Text()),
        sa.Column("ocorrido_em", sa.Date(), nullable=False),
        sa.Column("anexo_key", sa.String(300)),
        sa.Column("anexo_nome", sa.String(200)),
        sa.Column("anexo_tipo", sa.String(100)),
        sa.Column("anexo_tamanho", sa.Integer()),
        sa.Column("visivel_em", sa.Date()),
        sa.Column("avaliacao_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("avaliacao.id")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fato_observado_candidato_id", "fato_observado", ["candidato_id"])
    op.create_index("ix_fato_observado_ocorrido_em", "fato_observado", ["ocorrido_em"])
    op.create_index("ix_fato_observado_tipo", "fato_observado", ["tipo"])
    op.create_index("ix_fato_observado_avaliacao_id", "fato_observado", ["avaliacao_id"])
    op.create_index("ix_fato_observado_criado_em", "fato_observado", ["criado_em"])


def downgrade() -> None:
    op.drop_table("fato_observado")
    op.drop_table("avaliacao")
    op.drop_table("ciclo_avaliacao")
    for nome in ("status_avaliacao", "relacao_avaliador", "ocasiao_avaliacao",
                 "tipo_fato_observado"):
        postgresql.ENUM(name=nome).drop(op.get_bind(), checkfirst=True)
