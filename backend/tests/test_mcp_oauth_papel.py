"""O papel que o assistente carrega — o risco nº 1 de toda a implementação.

`permissoes_do_usuario` (auth_rh.py) lê `usuario.papel` **do objeto**. Se o
`/mcp` devolver o `UsuarioRH` do banco, a pessoa age com o papel do dia a dia
dela: **27 permissões em vez de 14**, incluindo `colaboradores:desligar` e
`colaboradores:efetivar`.

⚠️ **E nada daria erro** — as ferramentas passariam a funcionar MELHOR. Ninguém
abre chamado dizendo "o assistente conseguiu desligar um colaborador". É o
defeito de acesso a mais, que ninguém reporta (a lição da v2.86), e só um teste
o pega.

O segundo perigo é o inverso: mutar o objeto carregado da sessão e deixar o
commit acontecer **grava `assistente_rh` na linha real da pessoa** — ela perde o
acesso ao painel, e a causa fica noutro serviço, a três arquivos de distância.

stdlib pura (lê arquivos, não sobe a app), roda no CI.
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SERVICO = RAIZ / "app" / "services" / "mcp_oauth.py"
PERMISSOES = RAIZ / "app" / "services" / "permissoes.py"

falhas = []
fonte = SERVICO.read_text(encoding="utf-8")


def _sem_comentario(texto: str) -> str:
    """Remove comentários e docstrings antes de afirmar sobre o CÓDIGO.

    Sem isto, a asserção casaria com o comentário que EXPLICA a regra — e o
    teste reprovaria a própria documentação do conserto (a lição da v2.71).
    """
    sem_doc = re.sub(r'"""(?:.|\n)*?"""', "", texto)
    return "\n".join(l.split("#")[0] for l in sem_doc.splitlines())


codigo = _sem_comentario(fonte)


def teste_papel_do_token_e_o_do_assistente():
    m = re.search(r'^PAPEL_DO_TOKEN = "([^"]+)"', fonte, re.M)
    if m is None:
        falhas.append("PAPEL_DO_TOKEN não está declarado.")
    elif m.group(1) != "assistente_rh":
        falhas.append(
            f"PAPEL_DO_TOKEN é {m.group(1)!r}, deveria ser 'assistente_rh'. Com o "
            "papel do dia a dia, o assistente ganharia desligar e efetivar "
            "colaborador — e nada daria erro (doc 17 § 4.1).")


def teste_quem_pode_conectar():
    m = re.search(r"PAPEIS_QUE_PODEM_CONECTAR = frozenset\(\{(.*?)\}\)", fonte, re.S)
    if m is None:
        falhas.append("PAPEIS_QUE_PODEM_CONECTAR não está declarado.")
        return
    achados = set(re.findall(r'"([^"]+)"', m.group(1)))
    esperados = {"superadmin", "admin", "rh"}
    if achados != esperados:
        falhas.append(
            f"Quem pode conectar mudou: {sorted(achados)} (esperado "
            f"{sorted(esperados)}). Decisão do Bruno em 20/08/2026.")
    # `automacao` e `assistente_rh` são papéis de MÁQUINA — ninguém tem senha
    # neles. Incluí-los criaria o laço da conta de máquina conectando a si mesma.
    for maquina in ("automacao", "assistente_rh"):
        if maquina in achados:
            falhas.append(
                f"{maquina!r} é papel de MÁQUINA e não pode estar entre quem "
                "conecta — ninguém tem senha nele.")


def teste_o_papel_e_trocado_na_resolucao():
    """A constante certa não basta: o caminho de resolução tem que USÁ-LA.

    É a lição da v2.67 — teste que não executa a linha mutada não protege nada.
    Aqui: procurar a atribuição `papel=PAPEL_DO_TOKEN` dentro da função que
    devolve a identidade.
    """
    i = codigo.find("def identidade_do_access_token")
    if i < 0:
        falhas.append("identidade_do_access_token não existe.")
        return
    corpo = codigo[i:]
    if "papel=PAPEL_DO_TOKEN" not in corpo.replace(" ", ""):
        falhas.append(
            "identidade_do_access_token não força `papel=PAPEL_DO_TOKEN`. Sem "
            "isso a pessoa age com o papel dela (27 permissões) e NADA dá erro.")


def teste_devolve_objeto_novo_e_nao_o_do_banco():
    """Objeto transiente, nunca o carregado — nem mutado.

    Mutar o da sessão e deixar commitar reescreve o papel REAL da pessoa no
    banco. Objeto que nunca esteve na sessão não pode ser gravado por acidente.
    """
    i = codigo.find("def identidade_do_access_token")
    corpo = codigo[i:] if i >= 0 else ""
    if "return UsuarioRH(" not in corpo.replace(" ", "").replace("\n", " ").replace(
            "returnUsuarioRH(", "return UsuarioRH("):
        # comparação tolerante a quebra de linha
        if not re.search(r"return\s+UsuarioRH\(", corpo):
            falhas.append(
                "identidade_do_access_token não constrói um UsuarioRH novo. "
                "Devolver (ou mutar) o objeto da sessão grava o papel trocado na "
                "linha real da pessoa quando a sessão commitar.")
    for proibido in ("real.papel =", "usuario.papel =", "real.papel=", "usuario.papel="):
        if proibido in corpo:
            falhas.append(
                f"Atribuição {proibido!r} muta o objeto carregado da sessão — "
                "isso GRAVA o papel trocado na linha real da pessoa.")


def teste_audiencia_e_concessao_sao_conferidas():
    """RFC 8707 e a revogação — as duas checagens que o /mcp não pode perder."""
    i = codigo.find("def identidade_do_access_token")
    corpo = codigo[i:] if i >= 0 else ""
    if "mesmo_recurso" not in corpo:
        falhas.append(
            "identidade_do_access_token não confere a AUDIÊNCIA (RFC 8707). Sem "
            "isso, token emitido para outro serviço que compartilhe o "
            "SECRET_KEY é aceito aqui.")
    if "concessao" not in corpo or ".valido" not in corpo:
        falhas.append(
            "identidade_do_access_token não consulta a CONCESSÃO. É essa "
            "consulta que faz revogar surtir efeito dentro dos 10 min de vida "
            "do access — sem ela, 'revoguei e continuou funcionando'.")
    if "ativo" not in corpo:
        falhas.append("Usuário inativo precisa NEGAR (molde do token_automacao).")


def teste_o_papel_existe_no_catalogo():
    catalogo = PERMISSOES.read_text(encoding="utf-8")
    if '"assistente_rh", ' not in catalogo:
        falhas.append("O papel 'assistente_rh' sumiu do catálogo de permissões.")


for t in (teste_papel_do_token_e_o_do_assistente, teste_quem_pode_conectar,
          teste_o_papel_e_trocado_na_resolucao,
          teste_devolve_objeto_novo_e_nao_o_do_banco,
          teste_audiencia_e_concessao_sao_conferidas,
          teste_o_papel_existe_no_catalogo):
    t()

if falhas:
    print("FALHOU:")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("OK - o assistente carrega assistente_rh, so RH conecta, e o papel real "
      "da pessoa nao e tocado.")
