"""Toda rota que o MCP chama cai numa permissão que o papel do MCP TEM.

Nasceu de um defeito real desta leva: `erros_recentes` foi escrita sobre
`GET /rh/diagnostico/erros`, que exige `sistema:telemetria` — permissão que
NENHUM dos dois papéis do MCP tem. Ela teria respondido **403 para todo mundo,
sempre**, e nada denunciaria: o servidor sobe, a ferramenta aparece na lista, o
modelo a escolhe, e a pessoa recebe "esta ação não é permitida" achando que
pediu a coisa errada.

É a v2.88 numa porta nova: *item que sempre responde 403 ensina a equipe a
ignorar mensagem de erro* — e é justamente a mensagem de erro que precisa ser
levada a sério quando algo quebra de verdade.

⚠️ **A correção certa é a ferramenta caber no papel, não o papel crescer.** O
`assistente_rh` é estreito por desenho (§ 5.2 do 13-mcp-do-portal.md); alargá-lo
para acomodar uma ferramenta desfaz a razão de ele existir. Se a permissão que
falta for de diagnóstico e couber, conceda-a explicitamente — e escreva por quê.

stdlib pura (lê arquivos, não importa `app.main`), roda no CI.
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
SERVIDOR = RAIZ / "mcp" / "portal_rh_mcp" / "servidor.py"
PERMISSOES = RAIZ / "backend" / "app" / "services" / "permissoes.py"
API = RAIZ / "backend" / "app" / "api"

falhas = []


def permissoes_do_papel(chave: str) -> set[str]:
    texto = PERMISSOES.read_text(encoding="utf-8")
    i = texto.index(f'"{chave}", ')
    resto = texto[i:]
    m = re.search(r"permissoes=frozenset\(\{(.*?)\}\)", resto, re.S)
    assert m, f"não achei as permissões de {chave}"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def permissao_da_rota(caminho: str) -> str | None:
    """Acha o `exige("...")` da rota que o MCP chama.

    Casa o decorador pelo caminho com os parâmetros substituídos por `{...}` —
    o MCP monta a URL com f-string, a rota a declara com o nome do parâmetro.
    """
    padrao = re.sub(r"\{[^}]+\}", r"\{[^}]+\}", caminho)
    for arquivo in API.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for m in re.finditer(r'@router\.(get|post|put|delete)\("([^"]+)"', texto):
            if re.fullmatch(padrao, m.group(2)):
                trecho = texto[m.end():m.end() + 1200]
                dep = re.search(r'exige\("([^"]+)"\)', trecho)
                return dep.group(1) if dep else "SEM_PERMISSAO"
    return None


# Os caminhos que o servidor chama, lidos do próprio arquivo: uma lista à mão
# aqui envelheceria na primeira ferramenta nova, em silêncio.
fonte = SERVIDOR.read_text(encoding="utf-8")
caminhos = sorted(set(re.findall(r'["\']/(rh/[^"\'{}]*(?:\{[^}]+\}[^"\']*)*)["\']', fonte)))
caminhos = ["/" + c for c in caminhos]

if not caminhos:
    falhas.append("Não achei nenhuma chamada a /rh/ no servidor.py — o teste "
                  "estaria passando sem verificar nada.")

# O `assistente_rh` é o papel das pessoas do RH (v3.13); o `automacao` é o de
# máquina (v2.94) e é MENOR de propósito. A ferramenta precisa funcionar ao
# menos para o primeiro, senão não funciona para ninguém.
assistente = permissoes_do_papel("assistente_rh")

for caminho in caminhos:
    perm = permissao_da_rota(caminho)
    if perm is None:
        falhas.append(f"{caminho}: o MCP chama uma rota que não existe no "
                      "backend. Confira o caminho — a ferramenta responderia 404.")
    elif perm == "SEM_PERMISSAO":
        falhas.append(f"{caminho}: rota sem `exige(...)` declarado. O "
                      "test_permissoes_declaradas deveria ter pego isso antes.")
    elif perm not in assistente:
        falhas.append(
            f"{caminho} exige `{perm}`, que o papel `assistente_rh` NÃO tem — a "
            "ferramenta responderia 403 para todo mundo, sempre. Ou a ferramenta "
            "sai, ou a permissão é concedida DE PROPÓSITO (e o papel é estreito "
            "por desenho: § 5.2 do 13-mcp-do-portal.md).")

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK - as {len(caminhos)} rotas chamadas pelo MCP cabem no papel assistente_rh.")
