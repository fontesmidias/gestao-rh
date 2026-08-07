"""Completa o backfill do Informativo de Integração do efetivo que a
`d6f8b2c4e5a7` NÃO chegou a fazer.

POR QUE ESTA MIGRATION EXISTE
-----------------------------
A `d6f8b2c4e5a7` (v2.69) inseria em `assinatura` por SQL cru omitindo
`otp_tentativas` — coluna NOT NULL **sem server_default** (nasceu assim em
`66a5f1cd51a0`; o `default=0` mora no modelo Python e SQL cru não passa pelo
ORM). Em banco vazio o `INSERT ... SELECT` insere zero linhas e passa verde; com
gente real na base ele estoura `NotNullViolation`.

O estrago em produção (2026-08-06, entre 7h e 9h) não foi de dado: o
`docker-entrypoint.sh` tem `set -e` e roda `alembic upgrade head` ANTES do
`exec uvicorn`, então o alembic saindo com código 1 abortou o script e **a API
nunca subiu**. Do lado de quem usa, isso é indistinguível de "o backend não fala
com o banco" — e nenhum restart resolvia, porque a falha se repetia.

O banco ficou parado em `c5e7a9b1d3f4` (o valor `informativo_efetivo` já estava
no enum: aquela revisão usa `autocommit_block` e commitou). A intervenção manual
do Bruno destravou a cadeia e marcou `d6f8b2c4e5a7` como aplicada, mas **as
linhas do backfill não foram inseridas** — as que existem hoje vieram da própria
aplicação, via `gerar_docs_do_posto_e_regime`, que usa o ORM.

Como o alembic já considera `d6f8b2c4e5a7` aplicada, corrigir aquele arquivo não
o faz rodar de novo naquele banco: corrige o futuro, não o presente. Daí esta
revisão, que roda o MESMO recorte, agora com a coluna certa.

IDEMPOTENTE: o `NOT EXISTS` faz esta migration não duplicar nada de quem já
recebeu a ficha pela tela. Em banco novo (que já rodou a `d6f8b2c4e5a7`
corrigida) ela simplesmente não insere nada.

Revision ID: e9c1a3f5b7d2
Revises: d6f8b2c4e5a7
Create Date: 2026-08-06
"""

from alembic import op

revision = "e9c1a3f5b7d2"
down_revision = "d6f8b2c4e5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO assinatura (id, candidato_id, documento, aguardando_liberacao,
                                otp_tentativas)
        SELECT gen_random_uuid(), c.id, 'informativo_efetivo', TRUE, 0
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
    # (Mesmo critério da d6f8b2c4e5a7; as duas revisões produzem o mesmo tipo
    # de registro, então não há como distinguir a origem — nem é preciso.)
    op.execute("DELETE FROM assinatura WHERE documento = 'informativo_efetivo' "
               "AND assinado_em IS NULL")
