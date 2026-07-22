"""Limpar a colisão de status (item 1b), PARTE 2/2: migra os registros
existentes cujo `status` era ativo/desligado (o vínculo, que agora vive só na
`situacao`) para um status de FLUXO, por origem: importado do Tirvu ->
`importado`; efetivado aqui -> `aprovado`. Roda numa transação SEPARADA da que
adicionou `importado` ao enum (senão UnsafeNewEnumValueUsage). Os valores
ativo/desligado ficam órfãos no enum (o front já os ignora).

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-21
"""

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'importado' foi adicionado na revisão anterior; com
    # transaction_per_migration (env.py), aquela revisão já commitou e este
    # UPDATE, em transação própria, enxerga o valor com segurança.
    # importado do Tirvu -> 'importado' (nunca passou pelo funil daqui)
    op.execute("""
        UPDATE candidato
           SET status = 'importado'
         WHERE status IN ('ativo', 'desligado')
           AND origem = 'importacao'
    """)
    # o restante (efetivado aqui) -> 'aprovado' (admissão concluída)
    op.execute("""
        UPDATE candidato
           SET status = 'aprovado'
         WHERE status IN ('ativo', 'desligado')
    """)


def downgrade() -> None:
    # Sem retorno determinístico (perde-se fluxo x vínculo); o vínculo
    # permanece íntegro em `situacao`.
    pass
