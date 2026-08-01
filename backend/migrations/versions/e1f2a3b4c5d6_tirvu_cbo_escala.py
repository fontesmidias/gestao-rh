"""Dados do Tirvu que se perdiam na importação (v2.38): CBO do cargo, escala e
tratamento da jornada.

O RH sobe a lista de cargos e de jornadas copiada do Tirvu. O parser já lia
essas colunas e as jogava fora na hora de gravar — sobrava só o ID.

- **CBO** é o que distingue cargo HOMÔNIMO: nos dados reais, "AUXILIAR DE
  SERVIÇOS GERAIS" tem dois IDs ativos (514225 = limpeza, 763125 = produção) e
  87 pessoas usam esse mesmo texto. Sem o CBO gravado, a tela pede uma decisão
  sem mostrar o que a fundamenta.
- **Escala** ("Semanal") e **tratamento** ("BANCO DE HORAS") são do cadastro do
  Tirvu e decidem folha. Nome com prefixo `tirvu_` de propósito: a `escala` que
  já existe em `jornada` é METADADO INTERNO do parser (seg-sex, 12x36…), com
  outro vocabulário — fundir os dois faria o RH ler um valor achando que é o
  outro.

Aditiva: nenhuma coluna existente é tocada.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cargo_tirvu", sa.Column("cbo", sa.String(length=10), nullable=True))
    op.add_column("jornada", sa.Column("tirvu_escala", sa.String(length=40), nullable=True))
    op.add_column("jornada", sa.Column("tirvu_tratamento", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("jornada", "tirvu_tratamento")
    op.drop_column("jornada", "tirvu_escala")
    op.drop_column("cargo_tirvu", "cbo")
