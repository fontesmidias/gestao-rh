"""Migration que faz INSERT cru precisa listar TODA coluna NOT NULL sem default.

O incidente de 2026-08-06 (v2.69), entre 7h e 9h da manhã: o Bruno foi usar o
sistema e não conseguia logar. Do lado dele, "o backend não estava se
comunicando com o banco". O banco estava perfeito — a API é que não existia.

A `d6f8b2c4e5a7` inseria em `assinatura` por SQL cru assim:

    INSERT INTO assinatura (id, candidato_id, documento, aguardando_liberacao)

`otp_tentativas` é NOT NULL e **não tem server_default** (nasceu assim em
`66a5f1cd51a0`). O `default=0` mora no modelo Python — e SQL cru não passa pelo
ORM, então o default simplesmente não existe para essa instrução.

O que tornou isso invisível até chegar em produção: em banco VAZIO o
`INSERT ... SELECT` insere zero linhas e passa verde. É a armadilha do "só passa
em banco limpo" (v2.14) de cabeça para baixo — aqui o banco limpo ESCONDE o
defeito em vez de causá-lo. Todo teste local passou.

E o estrago não ficou contido na migration. O `docker-entrypoint.sh` tem
`set -e` e roda `alembic upgrade head` ANTES do `exec uvicorn`: alembic saindo
com código 1 aborta o script inteiro e o uvicorn nunca sobe. Cada restart do
container repetia a falha. O banco ficou parado uma revisão antes do head, com o
valor do enum já commitado (a revisão anterior usa `autocommit_block`).

Este teste é ESTRUTURAL: lê as migrations, encontra todo `INSERT INTO <tabela>
(colunas...)` e cobra que as colunas obrigatórias da tabela estejam na lista.
As colunas obrigatórias são derivadas do DDL das próprias migrations
(`op.create_table` + `op.add_column`), então a fonte é o que o BANCO tem — não o
modelo Python, que foi exatamente o engano.

Não precisa de banco nem de container: roda em segundos, no CI.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_migration_insert_cru.py
"""

import pathlib
import re
import sys

VERSOES = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"

FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


# --------------------------------------------------------------------------
# 1. Levantar, do DDL das migrations, as colunas NOT NULL SEM default por tabela
# --------------------------------------------------------------------------
# Uma coluna é obrigatória num INSERT cru quando é NOT NULL e não tem
# server_default. `nullable` sem menção explícita: no create_table o alembic
# sempre escreve `nullable=`, então a ausência é tratada como opcional (não
# inventamos obrigatoriedade — falso positivo travaria o CI sem defeito real).

RE_CREATE = re.compile(
    r"op\.create_table\(\s*[\"'](?P<tabela>\w+)[\"'](?P<corpo>.*?)\n\s*\)",
    re.S)
RE_COLUNA = re.compile(r"sa\.Column\(\s*[\"'](?P<nome>\w+)[\"'](?P<resto>[^\n]*)")
RE_ADD_COLUNA = re.compile(
    r"op\.add_column\(\s*[\"'](?P<tabela>\w+)[\"']\s*,\s*sa\.Column\("
    r"\s*[\"'](?P<nome>\w+)[\"'](?P<resto>[^\n]*)")


def _obrigatoria(resto: str) -> bool:
    """NOT NULL e sem server_default → precisa vir no INSERT."""
    if "nullable=False" not in resto:
        return False
    return "server_default" not in resto


def _ordem_das_revisoes() -> list[pathlib.Path]:
    """Migrations na ordem em que o alembic as executa (segue down_revision).

    A ordem importa: uma coluna obrigatória só vale para os INSERT das revisões
    SEGUINTES. Conferir contra o conjunto final produziria falso positivo — foi
    o que aconteceu com `roteiro_entrevista.tipo`, acrescentada na v2.67 com
    server_default, contra um INSERT da v2.66, quando a coluna nem existia.
    Teste que reprova código correto é pior que teste nenhum.
    """
    por_revisao: dict[str, tuple[pathlib.Path, str | None]] = {}
    for arq in VERSOES.glob("*.py"):
        texto = arq.read_text(encoding="utf-8")
        # As 4 migrations originais declaram com anotação de tipo
        # (`revision: str = '...'`); as demais, sem. Aceitar as duas formas —
        # sem isso a `66a5f1cd51a0`, que CRIA a `assinatura`, fica de fora e o
        # teste deixa de enxergar justamente a tabela do incidente.
        r = re.search(r"^revision(?::[^=]+)? = [\"']([^\"']+)[\"']", texto, re.M)
        d = re.search(r"^down_revision(?::[^=]+)? = [\"']([^\"']+)[\"']", texto, re.M)
        if r:
            por_revisao[r.group(1)] = (arq, d.group(1) if d else None)
    filhos = {pai: rev for rev, (_, pai) in por_revisao.items()}
    atual = next((r for r, (_, pai) in por_revisao.items()
                  if pai is None or pai not in por_revisao), None)
    ordem: list[pathlib.Path] = []
    vistos: set[str] = set()
    while atual and atual not in vistos:
        vistos.add(atual)
        ordem.append(por_revisao[atual][0])
        atual = filhos.get(atual)
    return ordem


def _coletar(texto: str, tabelas: dict[str, set[str]]) -> None:
    for m in RE_CREATE.finditer(texto):
        alvo = tabelas.setdefault(m.group("tabela"), set())
        for col in RE_COLUNA.finditer(m.group("corpo")):
            if _obrigatoria(col.group("resto")):
                alvo.add(col.group("nome"))
    for m in RE_ADD_COLUNA.finditer(texto):
        if _obrigatoria(m.group("resto")):
            tabelas.setdefault(m.group("tabela"), set()).add(m.group("nome"))


# --------------------------------------------------------------------------
# 2. Encontrar os INSERT crus e conferir a lista de colunas
# --------------------------------------------------------------------------
RE_INSERT = re.compile(
    r"INSERT\s+INTO\s+(?P<tabela>\w+)\s*\((?P<colunas>[^)]*)\)", re.I | re.S)


def main() -> int:
    print("Migrations com INSERT cru × colunas NOT NULL sem default\n")

    ordem = _ordem_das_revisoes()
    checar(len(ordem) > 50, f"cadeia de revisões percorrida ({len(ordem)} revisões)")

    # Percorre na ORDEM de execução: o DDL vai se acumulando, e cada INSERT é
    # conferido contra o schema que existia NAQUELE ponto da cadeia.
    obrigatorias: dict[str, set[str]] = {}
    encontrados = 0
    for arq in ordem:
        texto = arq.read_text(encoding="utf-8")
        for m in RE_INSERT.finditer(texto):
            tabela = m.group("tabela")
            if tabela not in obrigatorias:
                continue  # tabela criada fora do DDL rastreável; nada a cobrar
            encontrados += 1
            listadas = {c.strip().strip('"\'')
                        for c in m.group("colunas").split(",") if c.strip()}
            faltando = obrigatorias[tabela] - listadas
            checar(not faltando,
                   f"{arq.name}: INSERT em '{tabela}' lista as colunas "
                   f"obrigatórias{'' if not faltando else f' — FALTAM: {sorted(faltando)}'}")
        # O DDL da própria revisão vale para as SEGUINTES, não para o INSERT
        # que está nela (a coluna passa a existir ao fim do upgrade).
        _coletar(texto, obrigatorias)

    # Âncora: a coluna que causou o incidente precisa ser reconhecida como
    # obrigatória. Sem isto o teste passaria verde com o parser quebrado.
    checar("otp_tentativas" in obrigatorias.get("assinatura", set()),
           "assinatura.otp_tentativas é reconhecida como obrigatória")
    checar(encontrados > 0, "há INSERT cru rastreável para conferir")

    print()
    if FALHAS:
        print(f"{len(FALHAS)} FALHA(S):")
        for f in FALHAS:
            print("  - " + f)
        print("\nMigration que faz INSERT cru NÃO herda default do modelo Python.")
        print("Liste explicitamente toda coluna NOT NULL sem server_default.")
        return 1
    print("Tudo certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
