"""Papéis e permissões do painel (v2.86).

Cria a tabela `papel`, acrescenta `usuario_rh.papel` e semeia os papéis de
fábrica a partir de `services/permissoes.py`.

⚠️ **O backfill é o ponto delicado.** Todo usuário existente vira
`superadmin` — não `rh`. Parece o contrário do que um módulo de permissões
deveria fazer, e é deliberado:

- Quem já usava o painel **já podia fazer tudo**; rebaixar a `rh` no deploy
  tiraria acesso de quem estava operando, sem aviso e sem ninguém para
  reconceder (o único que poderia reconceder também teria sido rebaixado).
  A instalação ficaria SEM superadmin — travada por fora.
- Segurança que chega quebrando o trabalho de quem está no meio de uma
  admissão é revertida às pressas, e o que fica é nenhuma segurança.

O degrau real acontece na TELA: o Bruno abre Configurações → Usuários e baixa
cada um para o papel certo, vendo o que cada papel concede. Isso é decisão de
quem conhece a equipe — não de uma migration adivinhando por e-mail.

Este arquivo NÃO usa `INSERT ... SELECT` cru sem listar colunas obrigatórias
(a lição da v2.70, que derrubou a API em produção por duas horas): os inserts
abaixo nomeiam todas as colunas `NOT NULL`.
"""

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c7e9a1b3d5f8"
down_revision = "b3d5f7a9c2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "papel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chave", sa.String(50), nullable=False, unique=True),
        sa.Column("rotulo", sa.String(100), nullable=False),
        sa.Column("descricao", sa.String(400), nullable=True),
        sa.Column("permissoes", postgresql.JSONB(), nullable=False,
                  server_default="[]"),
        sa.Column("de_fabrica", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_papel_chave", "papel", ["chave"], unique=True)

    # `server_default` é obrigatório aqui: a coluna é NOT NULL e a tabela tem
    # linhas. Sem ele, o ALTER falha em qualquer banco com usuário cadastrado —
    # exatamente o caso da produção, e exatamente o defeito da v2.70.
    op.add_column("usuario_rh", sa.Column(
        "papel", sa.String(50), nullable=False, server_default="rh"))

    # --- Semeia os papéis de fábrica --------------------------------------
    #
    # Importar o catálogo aqui (e não repetir a lista) é o que evita a segunda
    # fonte de verdade que envelhece torto — o defeito do enum reescrito à mão
    # da v2.69, que ficou desatualizado sem ninguém perceber.
    from app.services.permissoes import PAPEIS_PADRAO, permissoes_padrao

    conexao = op.get_bind()
    for padrao in PAPEIS_PADRAO:
        # O superadmin fica com a lista VAZIA de propósito: `pode()` nem a
        # consulta. Guardar todas as chaves aqui faria a lista envelhecer a cada
        # módulo novo — e um superadmin com lista desatualizada é justamente o
        # que o desenho existe para impedir.
        chaves = ([] if padrao.tudo else sorted(permissoes_padrao(padrao.chave)))
        conexao.execute(
            sa.text("""
                INSERT INTO papel (id, chave, rotulo, descricao, permissoes,
                                   de_fabrica, criado_em)
                VALUES (gen_random_uuid(), :chave, :rotulo, :descricao,
                        CAST(:permissoes AS jsonb), true, now())
                ON CONFLICT (chave) DO NOTHING
            """),
            {"chave": padrao.chave, "rotulo": padrao.rotulo,
             "descricao": padrao.descricao, "permissoes": json.dumps(chaves)},
        )

    # --- Backfill: quem já existia continua podendo tudo -------------------
    # Ver o comentário no topo. Idempotente (`WHERE papel = 'rh'` só pega quem
    # acabou de receber o default), para o caso de a revisão ser reexecutada.
    conexao.execute(sa.text(
        "UPDATE usuario_rh SET papel = 'superadmin' WHERE papel = 'rh'"))


def downgrade() -> None:
    op.drop_column("usuario_rh", "papel")
    op.drop_index("ix_papel_chave", table_name="papel")
    op.drop_table("papel")
