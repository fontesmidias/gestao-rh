"""Escolaridade do talento: 60 → 300 caracteres (v2.89.1).

Defeito de campo: o Bruno não conseguia cadastrar talento à mão, e o log
mostrava `StringDataRightTruncation` com 104 caracteres —
"Técnico em Secretariado / Secretário Executivo; Inglês avançado (cursando,
Centro de Idiomas de Ceilândia)".

A coluna nasceu dimensionada para o formulário PÚBLICO, onde a escolaridade sai
de uma lista curta ("Ensino médio completo"). Quando o RH cadastra à mão, o
campo é texto livre — e o real não cabe. Coluna dimensionada para o caminho de
entrada mais estreito quebra no dia em que aparece o outro.

ALARGAR varchar não reescreve a tabela no Postgres nem invalida dado existente,
então não há risco para os registros que já estão lá. O `downgrade` volta a 60
e **truncaria** o que passar disso — por isso ele avisa em vez de apagar em
silêncio.
"""

import sqlalchemy as sa
from alembic import op

revision = "f2b5d7c9e3a1"
down_revision = "e1a4c6b8d2f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("talento", "escolaridade",
                    existing_type=sa.String(60), type_=sa.String(300),
                    existing_nullable=True)


def downgrade() -> None:
    # Voltar a 60 cortaria texto de gente real. Recusa explícita em vez de
    # truncar calado — dado perdido não se recupera do rollback (a regra da
    # v2.57: migração de dado de gente real guarda o original).
    conexao = op.get_bind()
    longos = conexao.execute(sa.text(
        "SELECT count(*) FROM talento WHERE length(escolaridade) > 60")).scalar() or 0
    if longos:
        raise RuntimeError(
            f"{longos} talento(s) têm escolaridade com mais de 60 caracteres; "
            "voltar a coluna truncaria o texto deles. Encurte os registros "
            "antes de rodar este downgrade.")
    op.alter_column("talento", "escolaridade",
                    existing_type=sa.String(300), type_=sa.String(60),
                    existing_nullable=True)
