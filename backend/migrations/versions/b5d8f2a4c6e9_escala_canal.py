"""Escala rotativa de canais (v2.91.1).

A aba "Escala Diária" da carteira: 5 postos (Demandas, E-mail, Teams, WhatsApp,
Retaguarda) girando entre a equipe num ciclo de 4 semanas, por cenário. É ela
que responde pelos processos 9.1 e 9.2 — cujo titular é a própria escala.

Sem esta tabela a tela dizia "Escala do dia" e não sabia dizer QUEM, que é
exatamente a informação que alguém procura ao abrir a carteira numa terça-feira.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b5d8f2a4c6e9"
down_revision = "a3c6e8f1b4d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "escala_canal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cenario", sa.String(4), nullable=False, server_default="C1"),
        sa.Column("semana", sa.Integer(), nullable=False),
        sa.Column("dia", sa.String(20), nullable=False),
        sa.Column("posto", sa.String(40), nullable=False),
        sa.Column("pessoa", sa.String(200), nullable=False),
        # Dois nomes no mesmo posto do mesmo dia fariam "quem está no WhatsApp
        # hoje?" ter duas respostas — que é o mesmo que não ter nenhuma.
        sa.UniqueConstraint("cenario", "semana", "dia", "posto",
                            name="uq_escala_posto"),
    )
    op.create_index("ix_escala_cenario", "escala_canal", ["cenario"])


def downgrade() -> None:
    op.drop_table("escala_canal")
