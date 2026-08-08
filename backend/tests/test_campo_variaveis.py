"""O seletor de variáveis está ligado nos editores que aceitam variável (v2.82).

Pedido do Bruno (2026-08-07):

    "Nos modelos, seja de email, mensagens, doc, mostrar todas as variáveis
     disponíveis de cada colaborador, para que de fato possa ser customizado
     cada modelo. Ou por exemplo, eu paro o cursor de digitação em determinado
     lugar do modelo e tenha como abrir um select com busca com as opções de
     variáveis, acho que melhora a ux e ui."

Antes, as variáveis eram uma LISTA NO TOPO da tela. A pessoa lia
`{{nome_social}}`, voltava ao texto e digitava de memória — com as duas chaves
de cada lado.

**Errar não dá erro em lugar nenhum.** O `fichas.aplicar_variaveis` usa regex
`{{(\\w+)}}` e só substitui o que casa com uma chave conhecida: `{{nome_socal}}`
(sem o "i") fica no texto **como está**, e sai IMPRESSO no PDF que a pessoa
assina — ou no e-mail, onde `{{codigo}}` mal digitado significa que ninguém
recebe o código de acesso. É a família do defeito silencioso: nada quebra, o
resultado é que está errado.

Este teste é ESTRUTURAL (lê o JSX, sem navegador) e trava três coisas:

1. **O componente existe e insere na posição do cursor.** A lógica que importa é
   `slice(0, at) + marcador + slice(at)` — sem ela o seletor viraria um
   "copiar" glorificado.
2. **A posição vem do DOM (`selectionStart`), guardada no `onBlur`.** Estado do
   React se perde quando o campo perde o foco — que é exatamente o que acontece
   ao clicar no seletor. Guardar depois seria tarde.
3. **Está ligado nos DOIS editores** (modelos de documento e textos de e-mail).
   Um só ficaria com o defeito antigo, e é o tipo de coisa que ninguém percebe
   até precisar.

Roda sem banco, sem rede e sem navegador.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_campo_variaveis.py
"""

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend" / "src"

FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


COMPONENTE = FRONT / "CampoComVariaveis.jsx"
checar(COMPONENTE.exists(), "o componente `CampoComVariaveis.jsx` existe")
if not COMPONENTE.exists():                      # pragma: no cover
    print("\ntest_campo_variaveis: 1 FALHA(S)")
    sys.exit(1)

fonte = COMPONENTE.read_text(encoding="utf-8")

print("\n1. insere na POSIÇÃO DO CURSOR")
checar("selectionStart" in fonte,
       "lê a posição do cursor do próprio campo (`selectionStart`), não de "
       "estado do React — estado se perde quando o campo perde o foco")
checar("onBlur" in fonte,
       "e guarda a posição no `onBlur`, ANTES de o foco ir para o seletor")
checar(".slice(0," in fonte and ".slice(at)" in fonte,
       "monta o texto novo com `slice(0, at) + marcador + slice(at)` — sem "
       "isso o seletor seria só um 'copiar' e a pessoa colaria à mão")
checar("setSelectionRange" in fonte,
       "devolve o cursor DEPOIS da variável inserida — senão a pessoa precisa "
       "clicar no texto de novo para continuar escrevendo")
checar("focus()" in fonte, "e devolve o FOCO ao campo de texto")

print("\n2. o marcador sai com as chaves duplas, sempre")
checar("`{{${nome}}}`" in fonte,
       "o marcador é montado pelo código (`{{nome}}`), não digitado — é o "
       "ponto da leva: não há o que escrever errado")

print("\n3. está ligado nos DOIS editores")
ligados = {
    "modelos de documento": FRONT / "rh" / "Modelos.jsx",
    "textos dos e-mails": FRONT / "rh" / "EmailsConfig.jsx",
}
for rotulo, arquivo in ligados.items():
    texto = arquivo.read_text(encoding="utf-8") if arquivo.exists() else ""
    checar("CampoComVariaveis" in texto,
           f"{rotulo} usa o componente ({arquivo.name})")
    # Dois usos: o campo curto (título/assunto) e o corpo. Um só significaria
    # que metade do editor ficou com o problema antigo.
    checar(texto.count("<CampoComVariaveis") >= 2,
           f"{rotulo}: nos DOIS campos que aceitam variável "
           f"(veio {texto.count('<CampoComVariaveis')})")

print("\n4. a lista do topo saiu de Modelos (não repetir a mesma coisa 3x)")
modelos = (FRONT / "rh" / "Modelos.jsx").read_text(encoding="utf-8")
checar("Variáveis disponíveis:" not in modelos,
       "a legenda do topo foi removida — a lista agora fica sob CADA campo, "
       "perto de onde se escreve")

print("\n5. o CSS das classes novas existe")
css = (FRONT / "styles.css").read_text(encoding="utf-8")
for classe in (".campo-variaveis", ".campo-variaveis-chips"):
    checar(classe in css,
           f"`{classe}` está no styles.css — classe fantasma não estiliza nada "
           f"(regra da v2.25)")

print()
if FALHAS:
    print(f"test_campo_variaveis: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_campo_variaveis: OK")
