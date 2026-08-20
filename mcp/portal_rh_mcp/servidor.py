"""As ferramentas que o Claude Desktop enxerga.

**A descrição de cada ferramenta é código, não comentário** (§ 8 do
13-mcp-do-portal.md): é o texto que o modelo lê para decidir se chama esta ou
outra. Descrição vaga faz a ferramenta errada ser chamada, e o sintoma aparece
como "o assistente não entendeu" — longe da causa. Por isso cada docstring diz
QUANDO usar e o que NÃO faz.

Todas as ferramentas são cascas finas sobre rotas que já existem (§ 11): a
regra de negócio mora no backend, onde a tela também a exerce. Reimplementar
qualquer decisão aqui faria as duas portas divergirem na primeira mudança — o
defeito que a v2.73 evitou no Banco de Talentos.
"""

from __future__ import annotations

# `MCPServer` é a classe do SDK 2.x; na 1.x ela se chamava `FastMCP`. O
# `pyproject.toml` crava a faixa maior de propósito — trocar de major
# aqui renomeia o import e o servidor deixa de subir (v3.00.4).
from mcp.server.mcpserver import MCPServer

from portal_rh_mcp.portal import ErroDoPortal, Portal
from portal_rh_mcp.saida import limpar

mcp = MCPServer("portal-rh")


def _portal() -> Portal:
    """Constrói o cliente a cada chamada, de propósito.

    Se o token for revogado enquanto o Desktop está aberto, a próxima chamada já
    lê o ambiente de novo — e um cliente guardado em variável de módulo faria o
    processo continuar tentando com a credencial velha até alguém reiniciar o
    Claude, com a mensagem de erro apontando para o lugar errado.
    """
    return Portal()


def _responder(fn):
    """Transforma `ErroDoPortal` em texto que o modelo repete para a pessoa.

    Deixar a exceção subir devolveria o traceback do Python ao contexto — que
    não diz o que RESOLVE (v2.93) e ainda gasta contexto com caminho de arquivo
    do computador de quem opera.
    """
    try:
        return fn()
    except ErroDoPortal as e:
        return {"erro": str(e)}


# ---------------------------------------------------------------- leitura


@mcp.tool()
def buscar_candidato(busca: str, incluir_colaboradores: bool = False) -> dict:
    """Acha pessoas em ADMISSÃO pelo nome, e-mail ou matrícula.

    Use como PRIMEIRO passo quando a pessoa citar alguém pelo nome: as demais
    ferramentas pedem o `id`, e é aqui que ele sai. Devolve uma lista resumida
    (nome, status, progresso dos documentos), não a ficha inteira.

    `incluir_colaboradores=True` alcança também quem já foi efetivado — a
    listagem padrão mostra só quem está em admissão, que é o recorte da tela.
    """
    return _responder(lambda: limpar({"encontrados": _portal().get(
        "/rh/candidatos", busca=busca,
        incluir_colaboradores=incluir_colaboradores or None)}))


@mcp.tool()
def diagnostico_candidato(candidato_id: str) -> dict:
    """Responde POR QUÊ: o retrato completo de uma pessoa em admissão.

    Numa chamada só: dados-chave, **por que o dossiê não gera**, o formulário
    que falta preencher, as fichas a assinar, a situação de cada documento e a
    linha do tempo. É a ferramenta certa para "por que o dossiê de fulano não
    sai?", "o que falta para essa admissão fechar?" e "o que aconteceu com essa
    pessoa?" — não chame três ferramentas para isso.

    O CPF sai mascarado. A linha do tempo vem dos 200 eventos mais recentes.
    """
    return _responder(lambda: limpar(
        _portal().get(f"/rh/candidatos/{candidato_id}/diagnostico")))


@mcp.tool()
def listar_admissoes(status: str | None = None, busca: str | None = None) -> dict:
    """A fila de trabalho da admissão: quem está em cada etapa.

    Use para "o que tem na minha fila hoje?" ou "quem está com documento
    pendente?". `status` aceita os valores do funil (por exemplo `convidado`,
    `docs_pendentes`, `envio_concluido`, `em_revisao`, `aprovado`); sem ele,
    vem a fila inteira.
    """
    return _responder(lambda: limpar(
        {"admissoes": _portal().get("/rh/candidatos", status=status, busca=busca)}))


@mcp.tool()
def pendencias_tirvu(busca: str | None = None,
                     incluir_importados: bool = False) -> dict:
    """O que impede a planilha de importação do Tirvu de ser aceita.

    O Tirvu RECUSA linha sem CTPS, PIS ou jornada, e a recusa acontece LÁ,
    depois do trabalho de montar o arquivo. Esta é a pré-checagem: devolve quem
    está incompleto e o que falta em cada um.

    ⚠️ Não gera nem baixa a planilha — exportar a base é ato de tela, por
    desenho (são CPF e salário de todo mundo num arquivo só).
    """
    return _responder(lambda: limpar(_portal().get(
        "/rh/colaboradores/tirvu-pendencias", busca=busca,
        incluir_importados=incluir_importados or None)))


@mcp.tool()
def erros_recentes(limite: int = 20) -> dict:
    """Falhas que o sistema registrou (dossiê que não gerou, e-mail que não saiu).

    Use quando a pessoa disser que "algo não funcionou" sem saber o quê. Mostra
    o erro e o candidato afetado, quando houver.
    """
    return _responder(lambda: limpar(
        {"erros": _portal().get("/rh/diagnostico/erros", limite=limite)}))


# ---------------------------------------------------------------- escrita


@mcp.tool()
def cadastrar_talento(
    nome: str,
    email: str | None = None,
    telefone: str | None = None,
    cargos_interesse: list[str] | None = None,
    resumo: str | None = None,
    origem: str | None = None,
    forcar: bool = False,
    motivo_sem_curriculo: str | None = None,
) -> dict:
    """Cadastra uma pessoa no Banco de Talentos (currículo que chegou por e-mail,
    indicação, contato por telefone).

    **Duplicata AVISA e não funde**: se já houver alguém com o mesmo e-mail (ou
    o mesmo nome+telefone), a resposta recusa DIZENDO QUEM É — id, nome, e-mail
    e situação. Nesse caso, **mostre a pessoa encontrada e pergunte** antes de
    repetir a chamada com `forcar=True`; homônimo real existe (a base tem mais
    de mil pessoas), mas quem decide é quem está operando, nunca você.

    **Não marque consentimento de LGPD**: quem cadastra é o RH, a pessoa não
    está na tela para concordar com nada, e o cadastro registra quem assumiu.
    Não há parâmetro para isso e não deve haver.

    O currículo em si sobe pela tela — esta ferramenta cria o registro. Quando
    ele ainda não existe, explique em `motivo_sem_curriculo` (fica na auditoria
    e como anotação no CRM), porque o currículo é obrigatório desde a v3.06.

    `origem` é a PROCEDÊNCIA em texto ("Currículo por e-mail", "Indicação do
    Gabriel"), não o nome de quem digitou.
    """
    corpo = {
        "nome": nome,
        "email": email,
        "telefone": telefone,
        "cargos_interesse": cargos_interesse or [],
        "resumo": resumo,
        "origem": origem,
        "forcar": forcar,
        "motivo_sem_curriculo": motivo_sem_curriculo,
    }
    corpo = {k: v for k, v in corpo.items() if v not in (None, [], "")}
    return _responder(lambda: limpar(_portal().post("/rh/talentos", corpo)))


def main() -> None:
    """Ponto de entrada do `portal-rh-mcp`.

    `stdio` porque o Claude Desktop sobe o servidor como processo filho e fala
    por entrada/saída padrão — não há porta aberta em lugar nenhum, que é
    justamente o que torna a v1 local mais barata de proteger que um endpoint
    público (§ 4).

    ⚠️ Nada pode ser impresso em `stdout` além do protocolo: um `print` de
    depuração corrompe a conversa e o sintoma aparece como "o servidor não
    conecta". Para depurar, escreva em `stderr`.
    """
    mcp.run()


if __name__ == "__main__":
    main()
