"""Roteiros de entrevista, modalidade e convite de calendário (v2.66).

Fase 3 do Módulo de Entrevistas (§ 14 de
`docs/planejamento/12-modulo-de-entrevistas.md`). Três coisas num commit:

1. **`roteiro_entrevista`** — o instrumento sai do código e vira dado. A
   migration **SEMEIA o roteiro padrão** a partir da constante `COMPETENCIAS`
   de `services/entrevistas.py`, já `padrao=True` e `status=publicado`: sem
   isso o primeiro `GET /formulario` depois do deploy abriria sem instrumento,
   e a entrevista em curso perderia a ficha no meio.

2. **`entrevista.roteiro_id` + `roteiro_snapshot`** — FK e snapshot, pelo mesmo
   motivo do `vaga_titulo`: editar o roteiro não pode reescrever a entrevista
   já feita.

3. **`modalidade`/`link_reuniao`/`sequencia_convite`/carimbos** — o convite de
   calendário e o lembrete.

**Sem enum novo no Postgres.** `status` do roteiro e `modalidade` são
`String(20)` com o enum do Python validando na entrada — é o que a `entrevista`
já fazia na `f8a9b0c1d2e3`. Não é preguiça: valor novo de enum no Postgres
exigiria DUAS revisões (o `transaction_per_migration` do `env.py` proíbe
`ADD VALUE` e uso na mesma transação), e "rascunho/publicado/arquivado" é um
vocabulário que ainda vai crescer.

**A semente é importada, não copiada.** Migration que copia o texto das âncoras
à mão passa a divergir da constante na primeira revisão dela, e ninguém
percebe — é a mesma lição do `test_export_dexion` ("comparar com cópia à mão
diverge do modelo na primeira revisão"). O `downgrade` foi executado de
verdade (up → down → up), não só escrito.

Revision ID: a1c3e5b7d9f2
Revises: f8a9b0c1d2e3
"""
import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1c3e5b7d9f2"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roteiro_entrevista",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("cargo", sa.String(120)),
        sa.Column("cargo_norm", sa.String(120)),
        sa.Column("senioridade", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="rascunho"),
        sa.Column("versao", sa.Integer, nullable=False, server_default="1"),
        sa.Column("competencias", postgresql.JSONB),
        sa.Column("padrao", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("publicado_em", sa.DateTime(timezone=True)),
        sa.Column("publicado_por", sa.String(200)),
        sa.Column("criado_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("criado_por", sa.String(200)),
        sa.Column("arquivado_em", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_roteiro_entrevista_cargo_norm", "roteiro_entrevista",
                    ["cargo_norm"])
    op.create_index("ix_roteiro_entrevista_status", "roteiro_entrevista", ["status"])
    op.create_index("ix_roteiro_entrevista_padrao", "roteiro_entrevista", ["padrao"])

    # ---- A SEMENTE: as 4 competências que eram o instrumento até a v2.65 ----
    # Importadas do serviço, nunca copiadas para cá.
    from app.services.entrevistas import (COMPETENCIAS_PADRAO,
                                          NOME_ROTEIRO_PADRAO)

    op.get_bind().execute(
        sa.text("""
            INSERT INTO roteiro_entrevista
                (id, nome, status, versao, competencias, padrao,
                 publicado_em, publicado_por, criado_por)
            VALUES
                (:id, :nome, 'publicado', 1, CAST(:comp AS jsonb), true,
                 now(), 'sistema (semente da migration)', 'sistema')
        """),
        {"id": str(uuid.uuid4()), "nome": NOME_ROTEIRO_PADRAO,
         "comp": json.dumps(COMPETENCIAS_PADRAO, ensure_ascii=False)})

    # ---- Entrevista: roteiro, modalidade e convite ----
    op.add_column("entrevista",
                  sa.Column("roteiro_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_entrevista_roteiro", "entrevista",
                          "roteiro_entrevista", ["roteiro_id"], ["id"],
                          ondelete="SET NULL")
    op.add_column("entrevista",
                  sa.Column("roteiro_snapshot", postgresql.JSONB))
    op.add_column("entrevista", sa.Column("modalidade", sa.String(20)))
    op.add_column("entrevista", sa.Column("link_reuniao", sa.String(500)))
    op.add_column("entrevista",
                  sa.Column("sequencia_convite", sa.Integer, nullable=False,
                            server_default="0"))
    op.add_column("entrevista",
                  sa.Column("convite_enviado_em", sa.DateTime(timezone=True)))
    op.add_column("entrevista",
                  sa.Column("lembrete_enviado_em", sa.DateTime(timezone=True)))

    # Entrevista que já existe e tem `local` preenchido era presencial — é o
    # único caso que o sistema sabia registrar antes desta versão. Quem não tem
    # local fica NULL (não se inventa modalidade: "não sei" é um estado, e
    # chutar `presencial` faria o e-mail prometer um endereço que não existe).
    op.execute("UPDATE entrevista SET modalidade = 'presencial' "
               "WHERE local IS NOT NULL AND modalidade IS NULL")


def downgrade() -> None:
    op.drop_column("entrevista", "lembrete_enviado_em")
    op.drop_column("entrevista", "convite_enviado_em")
    op.drop_column("entrevista", "sequencia_convite")
    op.drop_column("entrevista", "link_reuniao")
    op.drop_column("entrevista", "modalidade")
    op.drop_column("entrevista", "roteiro_snapshot")
    # A FK cai junto com a coluna; soltá-la antes evita depender da ordem.
    op.drop_constraint("fk_entrevista_roteiro", "entrevista", type_="foreignkey")
    op.drop_column("entrevista", "roteiro_id")
    op.drop_index("ix_roteiro_entrevista_padrao", table_name="roteiro_entrevista")
    op.drop_index("ix_roteiro_entrevista_status", table_name="roteiro_entrevista")
    op.drop_index("ix_roteiro_entrevista_cargo_norm", table_name="roteiro_entrevista")
    op.drop_table("roteiro_entrevista")
