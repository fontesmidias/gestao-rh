"""Backfill: cria o Informativo de Integração do efetivo para quem está com a
admissão EM ANDAMENTO.

Revisão SEPARADA da que criou o valor do enum de propósito: o `env.py` roda com
`transaction_per_migration=True` e o Postgres proíbe usar valor de enum
recém-criado na mesma transação (ver CLAUDE.md).

Recorte deliberado — só admissão aberta (status anterior a `aprovado`), pelo
mesmo motivo que a v2.43 não reabre checklist congelado: quem já foi aprovado
teve o dossiê gerado e, em muitos casos, efetivado. Criar uma assinatura
pendente nesses registros faria o sistema cobrar de gente que já concluiu a
admissão um documento que não existia quando ela aconteceu. O RH que quiser
emitir para alguém já aprovado usa a tela normalmente.

Nasce `aguardando_liberacao=True`, como o do intermitente: informativo de
integração só vai ao candidato quando o RH dispara (v1.92).

Revision ID: d6f8b2c4e5a7
Revises: c5e7a9b1d3f4
Create Date: 2026-08-05
"""

from alembic import op

revision = "d6f8b2c4e5a7"
down_revision = "c5e7a9b1d3f4"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
        INSERT INTO assinatura (id, candidato_id, documento, aguardando_liberacao)
        SELECT gen_random_uuid(), c.id, 'informativo_efetivo', TRUE
          FROM candidato c
         WHERE c.regime = 'efetivo'
           AND c.situacao IS NULL
           AND c.status::text IN ('convidado', 'preenchendo', 'docs_pendentes',
                                  'aguardando_assinatura', 'envio_concluido',
                                  'em_revisao')
           AND NOT EXISTS (
               SELECT 1 FROM assinatura a
                WHERE a.candidato_id = c.id
                  AND a.documento = 'informativo_efetivo'
                  AND a.invalidada_em IS NULL)
    """)


def downgrade() -> None:
    # Só remove o que nunca foi assinado — PDF assinado é peça de prova.
    op.execute("DELETE FROM assinatura WHERE documento = 'informativo_efetivo' "
               "AND assinado_em IS NULL")
