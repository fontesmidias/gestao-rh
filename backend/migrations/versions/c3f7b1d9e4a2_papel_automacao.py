"""Papel `automacao` (MCP) — semeia em banco que JÁ existe.

A semeadura de papéis roda na `c7e9a1b3d5f8`, que **já foi aplicada** em
produção. Migration aplicada não roda de novo (a lição da v2.70): acrescentar o
papel novo àquela lista conserta apenas bancos criados do zero, e o banco real —
o único que importa — nunca o receberia. Por isso esta revisão existe.

Idempotente (`ON CONFLICT DO NOTHING`) porque a `c7e9a1b3d5f8` também insere o
papel em bancos novos: os dois caminhos precisam conviver sem duplicar.

⚠️ **Não promove ninguém.** Cria o papel; quem o recebe é um usuário criado de
propósito para a automação, pela tela de usuários. Migration que atribui papel a
gente já existente é como se concede acesso sem ninguém decidir.

Revision ID: c3f7b1d9e4a2
Revises: b5d8f2a4c6e9
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "c3f7b1d9e4a2"
down_revision = "b5d8f2a4c6e9"
branch_labels = None
depends_on = None

CHAVE = "automacao"


def upgrade() -> None:
    # Importa o catálogo em vez de repetir a lista: segunda fonte de verdade
    # envelhece torto e em silêncio (o enum reescrito à mão da v2.69).
    from app.services.permissoes import PAPEIS_POR_CHAVE, permissoes_padrao

    padrao = PAPEIS_POR_CHAVE.get(CHAVE)
    if padrao is None:          # catálogo mudou: não inventa papel aqui
        return

    op.get_bind().execute(
        sa.text("""
            INSERT INTO papel (id, chave, rotulo, descricao, permissoes,
                               de_fabrica, criado_em)
            VALUES (gen_random_uuid(), :chave, :rotulo, :descricao,
                    CAST(:permissoes AS jsonb), true, now())
            ON CONFLICT (chave) DO NOTHING
        """),
        {"chave": padrao.chave, "rotulo": padrao.rotulo,
         "descricao": padrao.descricao,
         "permissoes": json.dumps(sorted(permissoes_padrao(CHAVE)))},
    )


def downgrade() -> None:
    # Só remove se ninguém estiver usando — apagar um papel em uso cortaria o
    # acesso de quem o tem, em silêncio (a razão do 409 da v2.87).
    op.get_bind().execute(sa.text("""
        DELETE FROM papel WHERE chave = :chave
          AND NOT EXISTS (SELECT 1 FROM usuario_rh WHERE papel = :chave)
    """), {"chave": CHAVE})
