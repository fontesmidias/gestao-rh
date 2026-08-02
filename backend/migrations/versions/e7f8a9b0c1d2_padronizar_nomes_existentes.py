"""Padroniza a capitalização dos nomes JÁ GRAVADOS (v2.57).

Decisão do Bruno em 2026-08-02: *"corrigir tudo automaticamente agora"*. A
v2.54 passou a padronizar na ENTRADA, mas quem já estava no banco continuava
torto — sobretudo os importados do Tirvu, que vêm todos em CAIXA ALTA.

⚠️ **Isto contraria a regra do CLAUDE.md** ("NÃO migre nome em lote"), que
existe porque reescrever dado de gente real sem conferência é o tipo de erro
que ninguém percebe. Foi decisão consciente do Bruno, ciente da ressalva. Por
isso a migração é feita de um jeito que a torna REVERSÍVEL:

* o nome ORIGINAL de cada registro alterado é guardado em
  `configuracao['nomes_backup_v257']` (JSON: id → nome antigo);
* o `downgrade()` restaura a partir desse backup, registro a registro — não é
  um "desfazer aproximado", é o valor exato que estava lá.

**O acento NÃO é inventado**: `MARIA DE FATIMA` vira `Maria de Fatima`, nunca
`Maria de Fátima` (decisão do Bruno na mesma conversa). O acento se perdeu na
origem, e adivinhar escreveria errado o nome de alguém — o que é pior que
deixá-lo sem acento. Fica para correção manual.

Só altera quem REALMENTE muda: se o nome já está no padrão, o registro não é
tocado (e não entra no backup).

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None

CHAVE_BACKUP = "nomes_backup_v257"

# (tabela, coluna, chave primária) que guardam nome de PESSOA. Endereço, cargo
# e afins ficam de fora de propósito: capitalizar "RUA DAS FLORES" é outra
# decisão, e cargo é casado por TEXTO com modelos/provas (mudar quebraria o
# casamento).
#
# A PK é declarada porque NÃO é sempre `id`: `dados_pessoais` é 1:1 com o
# candidato e usa `candidato_id`. Assumir `id` fazia a migração estourar no meio
# — e, pior, DEPOIS de já ter alterado as tabelas anteriores.
ALVOS = [
    ("candidato", "nome_completo", "id"),
    ("talento", "nome", "id"),
    ("dados_pessoais", "nome_mae", "candidato_id"),
    ("dados_pessoais", "nome_pai", "candidato_id"),
    ("dados_pessoais", "nome_social", "candidato_id"),
    ("dependente", "nome_completo", "id"),
    ("contato_emergencia", "nome_completo", "id"),
    ("crianca_creche", "nome", "id"),
]


def _capitalizar(texto):
    """Mesma função da aplicação — importada, nunca reescrita aqui.

    Duplicar a lógica na migração criaria duas regras de capitalização que
    divergiriam na primeira correção feita só de um lado.
    """
    from app.services.nomes import capitalizar_nome
    return capitalizar_nome(texto)


def upgrade() -> None:
    con = op.get_bind()
    backup: dict[str, str] = {}

    for tabela, coluna, pk in ALVOS:
        # A tabela pode não existir num banco parcial (ou o nome ter mudado):
        # a migração não pode derrubar o deploy por causa disso.
        if not con.dialect.has_table(con, tabela):
            continue
        linhas = con.execute(
            sa.text(f"SELECT {pk}, {coluna} FROM {tabela} "  # noqa: S608 — nomes fixos acima
                    f"WHERE {coluna} IS NOT NULL AND {coluna} <> ''")
        ).fetchall()
        for id_, valor in linhas:
            novo = _capitalizar(valor)
            if not novo or novo == valor:
                continue          # já está no padrão — não toca, não faz backup
            backup[f"{tabela}|{coluna}|{pk}|{id_}"] = valor
            con.execute(
                sa.text(f"UPDATE {tabela} SET {coluna} = :novo "  # noqa: S608
                        f"WHERE {pk} = :id"),
                {"novo": novo, "id": id_},
            )

    if not backup:
        return
    # Backup na config dinâmica (chave/valor), que já existe e não exige tabela
    # nova. É o que permite ao downgrade restaurar o valor EXATO.
    con.execute(
        sa.text("INSERT INTO configuracao (chave, valor) VALUES (:c, :v) "
                "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor"),
        {"c": CHAVE_BACKUP, "v": json.dumps(backup, ensure_ascii=False)},
    )


def downgrade() -> None:
    """Restaura os nomes exatamente como estavam antes do upgrade."""
    con = op.get_bind()
    linha = con.execute(
        sa.text("SELECT valor FROM configuracao WHERE chave = :c"),
        {"c": CHAVE_BACKUP},
    ).fetchone()
    if linha is None:
        return
    for chave, valor in json.loads(linha[0]).items():
        # `|` como separador, não `.`: o id é UUID e o nome da coluna poderia
        # conter ponto — com `.` o split devolveria pedaços errados e o
        # UPDATE restauraria o registro errado (ou nenhum), em silêncio.
        tabela, coluna, pk, id_ = chave.split("|", 3)
        con.execute(
            sa.text(f"UPDATE {tabela} SET {coluna} = :v WHERE {pk} = :id"),  # noqa: S608
            {"v": valor, "id": id_},
        )
    con.execute(sa.text("DELETE FROM configuracao WHERE chave = :c"), {"c": CHAVE_BACKUP})
