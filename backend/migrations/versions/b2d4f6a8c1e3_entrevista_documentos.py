"""Documentos, assinatura da ficha, triagem editável e duração (v2.67).

Fase 4 do Módulo de Entrevistas (§ 15 de
`docs/planejamento/12-modulo-de-entrevistas.md`). Quatro coisas:

1. **`assinatura_entrevista`** — a ficha de entrevista é assinável pelo RH que
   conduziu (§ 15.3). Tabela PRÓPRIA, e a escolha é deliberada: usar
   `solicitacao_assinatura` faria a ficha entrar no DOSSIÊ, porque
   `services/dossie.py` varre toda solicitação concluída com `pdf_final_key` sem
   filtrar `origem` — e o § 15.4 proíbe justamente isso. Ver o docstring de
   `app/models/assinatura_entrevista.py`.

2. **`entrevista.duracao_min`** — a duração do convite virou campo (§ 15.5 item
   4), alimentando o `DTEND` do `.ics`. `server_default='60'` para que a linha
   ANTIGA continue valendo uma hora, que é a constante que valia antes.

3. **`roteiro_entrevista.tipo` + `perguntas`** — a triagem entra no mesmo
   catálogo, como `tipo='triagem'` (§ 15.5 item 3), e **continua sem nota, sem
   competência e sem âncora**.

4. **Semeia o roteiro de TRIAGEM padrão** a partir de `PERGUNTAS_TRIAGEM`, já
   `publicado`. Sem a semente, a primeira triagem depois do deploy abriria sem
   pergunta nenhuma — o mesmo cuidado que a `a1c3e5b7d9f2` teve com o roteiro de
   entrevista.

**Sem enum novo no Postgres**: `tipo` é `String(20)` com o enum do Python
validando na entrada, como `status`/`modalidade` já fazem. Valor novo de enum no
Postgres exigiria DUAS revisões (o `transaction_per_migration` do `env.py`
proíbe `ADD VALUE` e uso na mesma transação).

**A semente é IMPORTADA, não copiada.** Migration que copia o texto das
perguntas à mão passa a divergir da constante na primeira revisão dela e
ninguém percebe — a mesma lição do `test_export_dexion`.

O `downgrade` foi executado de verdade (up → down → up), não só escrito.

Revision ID: b2d4f6a8c1e3
Revises: a1c3e5b7d9f2
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2d4f6a8c1e3"
down_revision = "a1c3e5b7d9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------- 1
    op.create_table(
        "assinatura_entrevista",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entrevista_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usuario_rh_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assinante_nome", sa.String(200), nullable=False),
        sa.Column("assinante_email", sa.String(200)),
        sa.Column("pdf_key", sa.String(300)),
        sa.Column("hash_sha256", sa.String(64)),
        sa.Column("prova_metodo", sa.String(40), nullable=False,
                  server_default="senha_sessao_rh"),
        sa.Column("ip", sa.String(45)),
        sa.Column("user_agent", sa.String(400)),
        sa.Column("via", sa.Integer, nullable=False, server_default="1"),
        sa.Column("substituida_em", sa.DateTime(timezone=True)),
        sa.Column("assinado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        # CASCADE: a entrevista excluída (que já passa pela lixeira) não deixa
        # assinatura órfã apontando para um registro inexistente.
        sa.ForeignKeyConstraint(["entrevista_id"], ["entrevista.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_rh_id"], ["usuario_rh.id"]),
    )
    op.create_index("ix_assinatura_entrevista_entrevista_id",
                    "assinatura_entrevista", ["entrevista_id"])

    # ---------------------------------------------------------------- 2
    # `server_default='60'` preenche as linhas existentes: a duração era a
    # constante `DURACAO_MIN = 60` até aqui, então o registro antigo continua
    # com exatamente o que ele significava.
    op.add_column("entrevista",
                  sa.Column("duracao_min", sa.Integer, nullable=False,
                            server_default="60"))

    # ---------------------------------------------------------------- 3
    op.add_column("roteiro_entrevista",
                  sa.Column("tipo", sa.String(20), nullable=False,
                            server_default="entrevista"))
    op.add_column("roteiro_entrevista",
                  sa.Column("perguntas", postgresql.JSONB))
    op.create_index("ix_roteiro_entrevista_tipo", "roteiro_entrevista", ["tipo"])

    # ---------------------------------------------------------------- 4
    # Semente do roteiro de TRIAGEM padrão, importada da constante.
    from app.services.entrevistas import NOME_TRIAGEM_PADRAO, PERGUNTAS_PADRAO

    conexao = op.get_bind()
    # Idempotente: banco que já tenha um roteiro de triagem (re-execução, dump
    # restaurado) não ganha um segundo padrão — dois fundos de herança fariam a
    # resolução escolher um deles por ordem de versão, em silêncio.
    ja_existe = conexao.execute(sa.text(
        "SELECT 1 FROM roteiro_entrevista WHERE tipo = 'triagem' LIMIT 1")).first()
    if not ja_existe:
        conexao.execute(
            sa.text("""
                INSERT INTO roteiro_entrevista
                    (id, nome, cargo, cargo_norm, senioridade, tipo, status,
                     versao, competencias, perguntas, padrao, publicado_em,
                     publicado_por, criado_em, criado_por)
                VALUES
                    (:id, :nome, NULL, NULL, NULL, 'triagem', 'publicado',
                     1, NULL, CAST(:perguntas AS jsonb), true, now(),
                     :por, now(), :por)
            """),
            {"id": str(uuid.uuid4()), "nome": NOME_TRIAGEM_PADRAO,
             "perguntas": json.dumps(PERGUNTAS_PADRAO),
             "por": "sistema (migração v2.67)"})


def downgrade() -> None:
    conexao = op.get_bind()
    # Só o que ESTA migration semeou. Apagar todo roteiro de triagem levaria
    # junto os que o RH tiver criado depois.
    conexao.execute(sa.text(
        "DELETE FROM roteiro_entrevista "
        "WHERE tipo = 'triagem' AND criado_por = 'sistema (migração v2.67)'"))

    op.drop_index("ix_roteiro_entrevista_tipo", table_name="roteiro_entrevista")
    op.drop_column("roteiro_entrevista", "perguntas")
    op.drop_column("roteiro_entrevista", "tipo")
    op.drop_column("entrevista", "duracao_min")
    op.drop_index("ix_assinatura_entrevista_entrevista_id",
                  table_name="assinatura_entrevista")
    op.drop_table("assinatura_entrevista")
