"""Guarda-corpo do sistema de design (v2.48).

`docs/planejamento/08-sistema-de-design.md` é um bom contrato — o problema
nunca foi falta de regra, foi **falta de aderência**. Entre a v2.24 e a v2.47
o mesmo punhado de defeitos voltou várias vezes, sempre pelo mesmo caminho:
alguém escreve uma tela nova copiando a vizinha, e a vizinha tem o valor
chutado.

Este teste é ESTRUTURAL (lê os arquivos, não precisa de banco nem navegador) e
cobra as regras que JÁ CUSTARAM correção:

1. **Classe fantasma** — classe usada no JSX que não existe no `styles.css`
   (v2.25: onze classes inventadas, a tela saía crua e o build passava).
2. **Token fantasma** — `var(--token)` que não existe no `:root`, e
   **fallback de cor** em `var()` (v2.46: `--texto-suave` deu 2,09:1 de
   contraste no tema escuro; o fallback fixo valia nos dois temas).
3. **Token de cor sem par escuro** — definido só no `:root` (v2.46:
   `--tinta-suave`, 12 usos, 3,61:1 no escuro).
4. **Tabela solta** — `.rh-tabela` sem o wrapper `.dash-scroll` (v2.48:
   `overflow-x` na própria `<table>` NÃO funciona — `display: table` ignora
   overflow; medido com Playwright).
5. **`<details>` remendado no JSX** — `cursor`/`list-style`/margem inline, que
   a regra base do `styles.css` já resolve (v2.47.1).

O que este teste deliberadamente NÃO faz: reprovar `style` inline de
espaçamento. São ~560 ocorrências herdadas; transformá-las em erro de CI
travaria o projeto sem consertar nada. A dívida está medida no CHANGELOG e é
paga aos poucos, tela por tela.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_design_system.py
"""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SRC = RAIZ / "frontend" / "src"
CSS = SRC / "styles.css"

FALHAS = []


def checar(ok: bool, descricao: str) -> None:
    print(("  ok   " if ok else "  FALHA ") + descricao)
    if not ok:
        FALHAS.append(descricao)


def jsx() -> list[pathlib.Path]:
    return sorted(p for p in SRC.rglob("*.jsx"))


fonte_css = CSS.read_text(encoding="utf-8")
# Comentários fora: `var(--nome)` aparece no cabeçalho do arquivo como exemplo
# de escrita, e seria lido como token inexistente.
css_sem_comentario = re.sub(r"/\*.*?\*/", "", fonte_css, flags=re.S)

# `:root { ... }` e o bloco do tema escuro, para conferir os pares de cor.
_bloco_claro = re.search(r":root\s*\{(.*?)\n\}", fonte_css, re.S)
_bloco_escuro = re.search(r":root\[data-tema=['\"]escuro['\"]\]\s*\{(.*?)\n\}",
                          fonte_css, re.S)
TOKENS_CLARO = set(re.findall(r"--([a-z0-9-]+)\s*:", _bloco_claro.group(1) if _bloco_claro else ""))
TOKENS_ESCURO = set(re.findall(r"--([a-z0-9-]+)\s*:", _bloco_escuro.group(1) if _bloco_escuro else ""))

# Custom properties setadas INLINE por desenho (valor vem do dado): o mecanismo
# é o correto — `--chip-cor` é consumida por `.chip`, `--card-cor` por
# `.dash-card`. Não são tokens globais e não precisam de par escuro.
DE_INSTANCIA = {"chip-cor", "card-cor"}


print("\n1. Classe usada no JSX existe no styles.css?")
# Só nomes literais: `className={...}` com expressão fica de fora (não dá para
# resolver estaticamente sem interpretar o JS).
usadas: dict[str, str] = {}
for arq in jsx():
    for m in re.finditer(r'className="([^"{}]+)"', arq.read_text(encoding="utf-8")):
        for cls in m.group(1).split():
            usadas.setdefault(cls, arq.name)

fantasmas = [
    f"{c} (em {arq})" for c, arq in sorted(usadas.items())
    if not re.search(r"\." + re.escape(c) + r"(?![\w-])", fonte_css)
]
checar(not fantasmas,
       "nenhuma classe fantasma"
       + ("" if not fantasmas else f" — {len(fantasmas)}: {', '.join(fantasmas[:6])}"))


print("\n2. Token usado existe, e nenhum var() de cor tem fallback?")
usados = set(re.findall(r"var\(\s*--([a-z0-9-]+)", css_sem_comentario))
for arq in jsx():
    usados |= set(re.findall(r"var\(\s*--([a-z0-9-]+)", arq.read_text(encoding="utf-8")))

inexistentes = sorted(usados - TOKENS_CLARO - DE_INSTANCIA)
checar(not inexistentes,
       "todo var(--token) existe no :root"
       + ("" if not inexistentes else f" — fantasma(s): {', '.join(inexistentes)}"))

# `var(--x, #hex)` congela a cor clara nos DOIS temas — foi o defeito exato do
# `--texto-suave`. Fallback que aponta para outro token é legítimo.
com_fallback_cor = re.findall(r"var\(\s*--[a-z0-9-]+\s*,\s*(#[0-9a-fA-F]{3,8})\s*\)", fonte_css)
checar(not com_fallback_cor,
       "nenhum var() com fallback de COR no styles.css"
       + ("" if not com_fallback_cor else f" — {len(com_fallback_cor)}: {', '.join(sorted(set(com_fallback_cor))[:6])}"))


print("\n3. Token de COR definido no claro tem par no escuro?")
# Só os que realmente pintam algo: nomes de espaçamento/tipografia/forma não
# invertem com o tema.
NAO_E_COR = ("esp-", "fs-", "raio", "fonte", "toque", "sombra")
# Cores de MARCA e de SINAL são as mesmas nos dois temas de propósito: o verde
# da Green House é o verde, e vermelho de perigo não vira outra coisa no
# escuro. Quem precisa inverter é SUPERFÍCIE e TEXTO (fundo, cartão, borda,
# tinta) — e é isso que este item protege.
DE_MARCA = {"verde", "verde-vivo", "verde-escuro", "erro", "ambar", "azul",
            "ok", "atencao", "perigo"}
cores_claro = {t for t in TOKENS_CLARO
               if not t.startswith(NAO_E_COR) and t not in DE_MARCA}
# Um token que só referencia outro (--ok: var(--verde)) herda o par do referido.
def _valor(tok: str, bloco: str) -> str:
    m = re.search(r"--" + re.escape(tok) + r"\s*:\s*([^;]+);", bloco)
    return (m.group(1) if m else "").strip()

sem_par = sorted(
    t for t in cores_claro
    if t not in TOKENS_ESCURO
    and not _valor(t, _bloco_claro.group(1)).startswith("var(")
    and re.search(r"var\(\s*--" + re.escape(t) + r"(?![\w-])", fonte_css)
)
checar(not sem_par,
       "todo token de cor USADO tem par no tema escuro"
       + ("" if not sem_par else f" — sem par: {', '.join(sem_par)}"))


print("\n4. Toda .rh-tabela está dentro de um .dash-scroll?")
# `display: table` IGNORA overflow — o wrapper é o único jeito de a tabela
# rolar dentro de si em vez de empurrar a página (medido em v2.46/v2.48).
soltas = []
for arq in jsx():
    linhas = arq.read_text(encoding="utf-8").split("\n")
    for i, linha in enumerate(linhas):
        if '<table className="rh-tabela"' not in linha:
            continue
        anterior = next((linhas[j] for j in range(i - 1, -1, -1) if linhas[j].strip()), "")
        if "dash-scroll" not in anterior:
            soltas.append(f"{arq.name}:{i + 1}")
checar(not soltas,
       "nenhuma tabela solta"
       + ("" if not soltas else f" — {len(soltas)}: {', '.join(soltas[:8])}"))


print("\n5. Nenhum <select> nativo? (toda lista suspensa é SelectBusca)")
# Pedido do Bruno em 2026-08-02, valendo daqui em diante: "toda vez que tiver
# um select, já imponha esse padrão". Ele tem 111 cargos, 269 jornadas e
# dezenas de postos — rolar até achar era a queixa nº 1 do dia a dia.
# O `SelectBusca` mostra o campo de busca só quando a lista justifica, então
# lista de 2 itens continua direta: o padrão de USO é único, muda a densidade.
nativos = []
for arq in jsx():
    if arq.name == "SelectBusca.jsx":
        continue
    for i, linha in enumerate(arq.read_text(encoding="utf-8").split("\n")):
        # Comentário que MENCIONA <select> não é uso — e falso positivo em
        # guarda-corpo ensina a ignorá-lo.
        if re.match(r"\s*(//|/?\*)", linha):
            continue
        if re.search(r"<select[\s>]", linha):
            nativos.append(f"{arq.name}:{i + 1}")
checar(not nativos,
       "nenhum <select> nativo no JSX"
       + ("" if not nativos else f" — {len(nativos)}: {', '.join(nativos[:8])}"))


print("\n6. <details>/<summary> sem remendo inline?")
# A regra base (summary { cursor; list-style-position: inside }) vive no
# styles.css desde a v2.47.1 — repetir no JSX é dívida que se multiplica.
remendos = []
for arq in jsx():
    for i, linha in enumerate(arq.read_text(encoding="utf-8").split("\n")):
        if ("<summary" in linha or "<details" in linha) and "style={{" in linha:
            if re.search(r"cursor|list-style|margin|padding", linha):
                remendos.append(f"{arq.name}:{i + 1}")
checar(not remendos,
       "nenhum <details>/<summary> com cursor/margem inline"
       + ("" if not remendos else f" — {len(remendos)}: {', '.join(remendos[:6])}"))

# A regra base tem que continuar existindo, senão o item acima vira armadilha:
# o teste passaria enquanto as telas perdiam o cursor.
checar(re.search(r"^summary\s*\{[^}]*cursor", fonte_css, re.M) is not None,
       "a regra base de summary (cursor) continua no styles.css")
checar(re.search(r"^summary\s*\{[^}]*list-style-position:\s*inside", fonte_css, re.M) is not None,
       "o marcador do summary continua `inside` (senão fura o padding do card)")


print()
if FALHAS:
    print(f"test_design_system: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_design_system: OK")
