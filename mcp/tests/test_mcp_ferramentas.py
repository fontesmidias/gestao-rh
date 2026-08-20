"""O servidor SOBE e registra as ferramentas que promete.

Por que este teste vive aqui e não em `backend/tests/`: ele precisa do SDK `mcp`
instalado, e a imagem da API não o tem (nem deve ter — o servidor roda no
computador de quem usa, não no VPS). Pô-lo no passo estrutural do `ci.yml`
derrubaria o CI por falta de dependência.

⚠️ **Importar a fachada não bastaria** (v3.00.6): `import portal_rh_mcp` ficaria
verde com as ferramentas todas quebradas. Aqui elas são LISTADAS pelo próprio
servidor — o caminho que o Claude Desktop percorre — e uma é CHAMADA de verdade
contra um portal que não existe, para provar que a falha sai como mensagem
acionável em vez de traceback.

Como rodar:
    cd mcp && pip install -e . && python tests/test_mcp_ferramentas.py
"""

import asyncio
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Antes de importar o servidor: o cliente valida o ambiente na construção, e sem
# isto o teste falharia por configuração, não por defeito.
os.environ.setdefault("PORTAL_RH_URL", "https://portal-que-nao-existe.invalid")
os.environ.setdefault("PORTAL_RH_TOKEN", "mcp_token_de_teste")

from portal_rh_mcp.servidor import mcp  # noqa: E402

# O contrato do § 6 do 13-mcp-do-portal.md: leitura para responder "por quê" e
# UMA porta de escrita, estreita. Ferramenta a mais não é melhoria — o doc diz
# "nada além disso na v1", e ferramenta demais degrada a escolha do modelo.
# ⚠️ `erros_recentes` saiu na v3.14 e não deve voltar sem a permissão: a rota
# exige `sistema:telemetria`, que NENHUM dos dois papéis do MCP tem — ela
# responderia 403 para todo mundo, sempre. Ferramenta que nunca funciona ensina
# quem opera a ignorar mensagem de erro (v2.88).
ESPERADAS = {
    "buscar_candidato", "diagnostico_candidato", "listar_admissoes",
    "pendencias_tirvu", "cadastrar_talento",
}

falhas = []


async def rodar():
    ferramentas = await mcp.list_tools()
    nomes = {f.name for f in ferramentas}

    if nomes - ESPERADAS:
        falhas.append(
            f"Ferramenta nao prevista no desenho: {sorted(nomes - ESPERADAS)}. "
            "O paragrafo 6 do 13-mcp-do-portal.md e o contrato: acrescente-a la "
            "(perguntando se o ato e reversivel e do dia a dia) antes de registrar.")
    if ESPERADAS - nomes:
        falhas.append(f"Ferramenta prometida e nao registrada: {sorted(ESPERADAS - nomes)}.")

    for f in ferramentas:
        # A descrição é o que o modelo lê para ESCOLHER a ferramenta (§ 8):
        # descrição fraca faz a ferramenta errada ser chamada, e o sintoma
        # aparece como "o assistente não entendeu" — longe da causa.
        if not f.description or len(f.description) < 120:
            falhas.append(f"{f.name}: descricao curta demais para o modelo "
                          "decidir quando usa-la.")
        # Nenhuma ferramenta recebe o token por parâmetro: ele vem do ambiente
        # justamente para o modelo não o ver — e portanto não ter como vazá-lo
        # numa resposta. Um parâmetro desses é fácil de acrescentar sem perceber.
        campos = set((f.input_schema or {}).get("properties", {}))
        if campos & {"token", "credencial", "authorization", "senha", "url"}:
            falhas.append(f"{f.name} aceita credencial/endereco por parametro. "
                          "Isso poe o segredo no contexto do modelo — ele vem do "
                          "ambiente, sempre.")

    # Chamada real contra um endereço que não resolve: a falha tem que voltar
    # como texto que diz o que RESOLVE (v2.93), nunca como exceção subindo.
    texto = str(await mcp.call_tool("listar_admissoes", {}))
    if "erro" not in texto.lower():
        falhas.append("Portal fora do ar nao virou mensagem de erro — a "
                      "ferramenta devolveu algo que parece resposta boa.")
    if "portal-que-nao-existe.invalid" not in texto:
        falhas.append("A mensagem de erro nao diz QUAL endereco falhou. Sem isso, "
                      "quem opera nao sabe que o config esta errado.")


asyncio.run(rodar())

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print(f"OK - {len(ESPERADAS)} ferramentas registradas, descritas, sem segredo em "
      "parametro, e com erro acionavel.")
