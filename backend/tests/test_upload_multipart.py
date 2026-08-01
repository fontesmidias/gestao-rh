"""Upload de arquivo nunca pode passar pelo `req()` do api.js (v2.39.1).

Bug de campo em 2026-08-01: os dois cards novos de importação do Tirvu
respondiam *"Não foi possível ler o arquivo (dados_invalidos)"*. O log do
servidor mostrava a coisa mais enganosa possível — `422 Field required` para o
campo `arquivo`, com o multipart **inteiro** impresso logo ao lado, arquivo,
nome e conteúdo à vista.

A causa: `_req()` força `Content-Type: application/json` em toda chamada. Com
`FormData`, quem precisa escrever o cabeçalho é o NAVEGADOR, porque só ele sabe
o `boundary` que separa as partes. Sobrescrito o cabeçalho, o boundary some, o
FastAPI não consegue separar as partes e conclui que o campo não veio.

Os uploads antigos (colaboradores, ponto, currículo) sempre usaram `buscar()`
direto — é a razão de funcionarem. A regra nunca esteve escrita, então o
próximo upload repetiria o erro; agora está aqui.

Este teste é ESTRUTURAL: lê o `api.js` e cobra a regra de toda função que monta
`FormData`. Não precisa de banco nem de navegador.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_upload_multipart.py
"""

import pathlib
import re

API_JS = (pathlib.Path(__file__).resolve().parents[2]
          / "frontend" / "src" / "api.js")

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


fonte = API_JS.read_text(encoding="utf-8")
linhas = fonte.splitlines()

# Cada `new FormData()` abre um trecho de upload. O corpo da função vai daí até
# a próxima definição de propriedade no mesmo nível — o suficiente para ver com
# que função a requisição é feita.
inicios = [i for i, l in enumerate(linhas) if "new FormData(" in l]
print(f"\n[{len(inicios)} uploads encontrados em api.js]")
checar(len(inicios) >= 5, "o arquivo tem uploads para conferir (a busca não quebrou)")

for i in inicios:
    # Nome da função: a linha de declaração mais próxima acima.
    nome = "?"
    for j in range(i, max(i - 12, -1), -1):
        m = re.match(r"\s*(\w+):\s*(async\s*)?\(", linhas[j])
        if m:
            nome = m.group(1)
            break
    corpo = []
    for l in linhas[i:i + 14]:
        # Para na próxima propriedade do objeto: sem isto o trecho invade a
        # função seguinte e acusa upload correto por causa do vizinho.
        if corpo and re.match(r"\s{2}\w+:\s", l):
            break
        # Comentário citando `req()` não é chamada — este teste existe
        # justamente porque o comentário ao lado EXPLICA a regra.
        corpo.append(re.sub(r"//.*$", "", l))
    trecho = "\n".join(corpo)

    usa_req = re.search(r"(?<![\w.'\"`])req\s*\(", trecho) is not None
    usa_buscar = "buscar(" in trecho
    checar(not usa_req,
           f"{nome}: monta FormData e NÃO usa req() — req() força "
           "Content-Type: application/json e apaga o boundary do multipart")
    checar(usa_buscar or not usa_req,
           f"{nome}: envia por buscar(), deixando o navegador escrever o "
           "Content-Type com o boundary")

# A regra só vale enquanto `_req` realmente forçar o cabeçalho: se um dia ele
# passar a respeitar FormData, este teste vira ruído — e o comentário abaixo
# diz onde olhar.
checar("'Content-Type': 'application/json'" in fonte,
       "o motivo da regra continua no código (_req força o cabeçalho JSON); "
       "se isso mudar, revise este teste")

print()
if FALHAS:
    print(f"test_upload_multipart: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_upload_multipart: OK")
