"""Toda `api.x(...)` chamada no front EXISTE no `api.js` — e recebe o que espera.

Por que este teste existe (v2.73, defeito relatado pelo Bruno em produção):

    "a msg abaixo aparece, no módulo de entrevistas quando clico em triagem ou
     entrevista — 😕 Algo deu errado ao abrir esta página"

Era o ErrorBoundary. O formulário de nova entrevista chamava **`api.talentos()`,
uma função que nunca existiu** (a certa é `listarTalentos`). O `.catch(() => {})`
ao lado não protegia nada: `undefined()` é `TypeError` **síncrono**, estourado
antes de existir promessa para capturar — e uma exceção de render apaga a TELA
INTEIRA, não o bloco.

É a mesma família da `prop` inventada no `SelectBusca` (v2.64) e da classe CSS
fantasma (v2.25): o JSX fica plausível, o build passa, e nada confere se o nome
existe do outro lado. JavaScript não avisa.

**E o defeito tinha uma segunda metade, mais silenciosa.** As três rotas daquele
`useEffect` devolvem LISTA PURA (`-> list[dict]`), mas o código lia
`r.itens || r.vagas || []` — então, mesmo sem o `TypeError`, os seletores de
pessoa, vaga e candidato abririam **VAZIOS, sem erro nenhum**. Seletor vazio
parece "não há nada cadastrado"; ninguém abre um chamado por isso. Por isso o
bloco 2 existe: corrigir só o nome deixaria dois terços do defeito de pé.

O que este teste NÃO faz: conferir o formato de retorno de toda chamada (exigiria
executar o front). Ele trava (1) a existência do nome — mecânico e exaustivo — e
(2) o caso específico das listas puras já conhecidas, com o nome da rota no erro.

Roda sem banco, sem rede e sem navegador: lê os arquivos.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_api_front_existe.py
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend" / "src"
API_JS = FRONT / "api.js"

FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


if not API_JS.exists():                      # pragma: no cover
    print(f"api.js não encontrado em {API_JS}")
    raise SystemExit(1)

fonte_api = API_JS.read_text(encoding="utf-8")

# Propriedades do objeto exportado: linhas com exatamente 2 espaços de indentação
# (`  nome:`). É como o arquivo é escrito do começo ao fim — chaves aninhadas têm
# indentação maior e não entram.
DEFINIDOS = set(re.findall(r"^\s{2}([A-Za-z_]\w*):", fonte_api, re.M))

print("\n1. nenhuma chamada `api.x(...)` aponta para função que não existe")
checar(len(DEFINIDOS) > 50,
       f"o extrator achou as funções do api.js ({len(DEFINIDOS)}) — se cair para "
       f"perto de zero, o formato do arquivo mudou e o teste virou decoração")

def _sem_comentarios(codigo: str) -> str:
    """Comentário que EXPLICA a regra não pode ser confundido com violação dela.

    Achado na v2.98.4: um comentário dizendo *"mesma família do `api.x()`
    inexistente"* fez este teste reprovar o `BotaoBaixar.jsx` — ele acusou como
    chamada real a MENÇÃO ao defeito, no arquivo que o conserta. É a armadilha
    da v2.71 (teste estrutural que reprova a documentação do próprio conserto),
    e o reflexo errado seria apagar o comentário.
    """
    codigo = re.sub(r"\{/\*.*?\*/\}", "", codigo, flags=re.S)   # comentário JSX
    codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.S)        # bloco /* */
    return re.sub(r"^\s*//.*$", "", codigo, flags=re.M)           # linha //


faltando: dict[str, set[str]] = {}
for arquivo in sorted(FRONT.rglob("*.jsx")):
    texto = _sem_comentarios(arquivo.read_text(encoding="utf-8"))
    for m in re.finditer(r"\bapi\.([A-Za-z_]\w*)\s*\(", texto):
        nome = m.group(1)
        if nome not in DEFINIDOS:
            faltando.setdefault(nome, set()).add(arquivo.name)

checar(not faltando,
       "toda `api.x(...)` do front existe no api.js"
       + (f" — INEXISTENTES: { {k: sorted(v) for k, v in faltando.items()} }"
          if faltando else ""))

# --------------------------------------------------------------------------
print("\n2. rota que devolve LISTA PURA não é lida como se fosse objeto")
# --------------------------------------------------------------------------
# Estas três rotas são `-> list[dict]` no backend (conferido no código, não
# suposto). Ler `r.itens` delas devolve `undefined` -> `[]`: o seletor abre vazio
# e ninguém percebe. Se um dia a rota passar a devolver `{itens: [...]}`, este
# teste falha e obriga a decidir conscientemente — que é o ponto.
ROTAS_LISTA = {
    "listarTalentos": "/rh/talentos",
    "vagas": "/rh/vagas",
    "candidatos": "/rh/candidatos",
}
for func, rota in ROTAS_LISTA.items():
    checar(func in DEFINIDOS, f"`api.{func}` existe (serve {rota})")

# O padrão errado é `.then((r) => setX(r.itens || ...))` SEM tratar array.
# Procura-se o uso de cada função e confere-se que o consumo tolera lista.
suspeitos: list[str] = []
for arquivo in sorted(FRONT.rglob("*.jsx")):
    texto = arquivo.read_text(encoding="utf-8")
    for func in ROTAS_LISTA:
        for m in re.finditer(rf"api\.{func}\([^)]*\)\s*\.then\(([^\n]*)", texto):
            trecho = m.group(1)
            # tolera lista se usa Array.isArray, um helper de lista, ou passa a
            # resposta direto (`.then(setX)`).
            if "Array.isArray" in trecho or "_lista" in trecho:
                continue
            if re.search(r"\.then\(set\w+\)", m.group(0)):
                continue
            if re.search(r"r\.(itens|vagas|talentos|candidatos)", trecho):
                suspeitos.append(f"{arquivo.name}: api.{func} lido como objeto -> {trecho.strip()[:60]}")

checar(not suspeitos,
       "nenhuma rota de lista pura é lida como `r.itens` (seletor vazio silencioso)"
       + (f" — {suspeitos}" if suspeitos else ""))

# --------------------------------------------------------------------------
print("\n3. o caso que derrubou a tela não volta")
# --------------------------------------------------------------------------
# Âncora explícita: `api.talentos` foi o nome inventado. Vale como regressão
# nomeada — o bloco 1 já pegaria, mas aqui o erro DIZ qual foi o defeito.
entrevistas = FRONT / "rh" / "EntrevistasRH.jsx"
if entrevistas.exists():
    txt = entrevistas.read_text(encoding="utf-8")
    # Só em CÓDIGO: o comentário que explica o defeito cita o nome de propósito,
    # e reprovar por causa dele faria apagar a explicação (armadilha da v2.71).
    codigo = "\n".join(
        linha.split("//", 1)[0] for linha in txt.splitlines()
        if not linha.strip().startswith("//"))
    checar("api.talentos(" not in codigo,
           "EntrevistasRH não voltou a chamar `api.talentos()` (era `listarTalentos`)")

print()
if FALHAS:
    print(f"test_api_front_existe: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_api_front_existe: OK")
