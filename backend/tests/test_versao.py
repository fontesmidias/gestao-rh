"""A versão do código não pode divergir do CHANGELOG.

Teste ESTRUTURAL (stdlib pura, sem app.main, roda em segundos no CI — mesma
regra do `test_design_system.py`). Ele existe por um motivo específico e
comprovado: o marcador de versão deste projeto já congelou DUAS vezes.

  1. `VERSAO_DEPLOY` parou em `v1.50` e ficou vinte versões mentindo. Na v2.28
     alguém percebeu, consertou o campo VIZINHO (`migracoes.no_codigo`, que
     passou a ser lido do diretório de migrations) e escreveu no docstring que
     a constante chumbada era o mau exemplo — mas deixou a constante.
  2. Ela congelou de novo, agora em `v2.27`, por mais vinte e seis versões, até
     o Bruno abrir `/api/health` depois de um deploy e ler a versão errada.

A lição das duas vezes é a mesma: documentar que uma constante precisa ser
atualizada à mão NÃO funciona. O que funciona é falhar o build.

Por que comparar com o CHANGELOG e não gerar a versão a partir dele: o
`CHANGELOG.md` está na raiz do repositório e o contexto de build da imagem da
API é `./backend`, então ele não entra na imagem (ver `app/versao.py`). O
CHANGELOG é a fonte de verdade para o HUMANO; `app/versao.py` é a fonte para o
RUNTIME; este teste é o que mantém os dois iguais.
"""
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CHANGELOG = RAIZ / "CHANGELOG.md"
VERSAO_PY = RAIZ / "backend" / "app" / "versao.py"

falhas: list[str] = []


def _versao_do_changelog() -> tuple[str, str] | None:
    """(versão, título) do topo do CHANGELOG — ex. ('2.53.0', 'Ver como...').

    Casa a PRIMEIRA linha `## [x.y.z] — data — título`, que por convenção do
    Keep a Changelog é sempre a mais recente.
    """
    texto = CHANGELOG.read_text(encoding="utf-8")
    for linha in texto.splitlines():
        m = re.match(r"^##\s*\[(\d+\.\d+\.\d+)\]\s*[—-]\s*[\d-]+\s*[—-]\s*(.+)$", linha)
        if m:
            return m.group(1), m.group(2).strip()
        # Entrada sem título (só versão e data) ainda serve para a versão.
        m = re.match(r"^##\s*\[(\d+\.\d+\.\d+)\]", linha)
        if m:
            return m.group(1), ""
    return None


def _constante(nome: str) -> str | None:
    """Lê `NOME = "valor"` de `app/versao.py` sem importar o módulo."""
    texto = VERSAO_PY.read_text(encoding="utf-8")
    m = re.search(rf'^{nome}\s*=\s*"([^"]*)"', texto, re.MULTILINE)
    return m.group(1) if m else None


def test_versao_bate_com_o_changelog() -> None:
    if not CHANGELOG.exists():
        falhas.append(f"CHANGELOG.md não encontrado em {CHANGELOG}")
        return
    if not VERSAO_PY.exists():
        falhas.append(f"app/versao.py não encontrado em {VERSAO_PY}")
        return

    topo = _versao_do_changelog()
    if topo is None:
        falhas.append("não achei nenhuma entrada '## [x.y.z]' no CHANGELOG.md")
        return
    versao_changelog, titulo_changelog = topo

    versao_codigo = _constante("VERSAO")
    if versao_codigo is None:
        falhas.append("app/versao.py não declara VERSAO = \"x.y.z\"")
    elif versao_codigo != versao_changelog:
        falhas.append(
            f"VERSAO divergente: app/versao.py diz {versao_codigo!r} e o topo do "
            f"CHANGELOG.md diz {versao_changelog!r}.\n"
            "    Ao fechar uma versão, atualize os DOIS — é exatamente o passo que "
            "foi esquecido nas v1.50 e v2.27, deixando /api/health mentir por "
            "dezenas de versões."
        )

    # O nome é conferência mais frouxa (o título do CHANGELOG às vezes é longo
    # demais para caber na tela), mas vazio com título disponível é esquecimento.
    nome_codigo = _constante("VERSAO_NOME")
    if titulo_changelog and not nome_codigo:
        falhas.append(
            f"VERSAO_NOME está vazio, mas o CHANGELOG tem título: {titulo_changelog!r}"
        )


def test_ninguem_mais_chuma_versao_a_mao() -> None:
    """`VERSAO_DEPLOY` não pode voltar como literal em `api/health.py`.

    Mutação que este teste pega: alguém "simplifica" reintroduzindo a string no
    health.py — o `/api/health` volta a congelar sem que nada acuse.
    """
    health = RAIZ / "backend" / "app" / "api" / "health.py"
    if not health.exists():
        falhas.append(f"api/health.py não encontrado em {health}")
        return
    texto = health.read_text(encoding="utf-8")
    if re.search(r'^VERSAO_DEPLOY\s*=\s*"', texto, re.MULTILINE):
        falhas.append(
            "api/health.py voltou a chumbar VERSAO_DEPLOY como string literal. "
            "Importe de app.versao — foi o chumbado que congelou duas vezes."
        )


if __name__ == "__main__":
    test_versao_bate_com_o_changelog()
    test_ninguem_mais_chuma_versao_a_mao()
    if falhas:
        print("FALHOU:")
        for f in falhas:
            print(f"  - {f}")
        sys.exit(1)
    print("OK: versão do código bate com o CHANGELOG.")
