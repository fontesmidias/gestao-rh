"""Papel `assistente_rh` (MCP com pessoas do RH) — semeia em banco que JÁ existe.

Mesma razão da `c3f7b1d9e4a2`: a semeadura de papéis (`c7e9a1b3d5f8`) já foi
aplicada em produção, e migration aplicada não roda de novo (v2.70).
Acrescentar o papel àquela lista consertaria só bancos criados do zero — o banco
real, que é o único que importa, nunca o receberia.

Por que este papel existe, e não o `automacao`: em 19/08/2026 o uso do MCP
mudou. Deixou de ser a Claude do Bruno lendo currículos e passou a ser a **equipe
do RH no Claude Coworking, executando tarefas por prompt**. O `automacao` é
estreito de propósito (4 permissões, só diagnóstico) e alargá-lo desfaria a razão
de ele existir — então este nasce ao lado, com o dia a dia da admissão e da
seleção, e sem nada que mude vínculo, decida dinheiro ou configure o sistema.

⚠️ **Não promove ninguém**, como a `c3f7b1d9e4a2`: cria o papel e para aí. Cada
pessoa do RH recebe o papel pela tela de usuários e emite a PRÓPRIA credencial —
é o token por pessoa que faz a auditoria responder "quem mandou?".

Revision ID: d4e8b2f6a9c1
Revises: b5d9e2a7c134
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "d4e8b2f6a9c1"
down_revision = "b5d9e2a7c134"
branch_labels = None
depends_on = None

CHAVE = "assistente_rh"


def upgrade() -> None:
    # Importa do catálogo em vez de repetir a lista: segunda fonte de verdade
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
    # Só remove se ninguém estiver usando — apagar papel em uso cortaria o
    # acesso de quem o tem, em silêncio (a razão do 409 da v2.87).
    op.get_bind().execute(sa.text("""
        DELETE FROM papel WHERE chave = :chave
          AND NOT EXISTS (SELECT 1 FROM usuario_rh WHERE papel = :chave)
    """), {"chave": CHAVE})
