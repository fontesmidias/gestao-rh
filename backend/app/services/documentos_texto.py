"""Corpo EDITÁVEL dos documentos de texto do sistema (v2.16).

Quando o RH duplica um documento do sistema, ele recebe um `ModeloDocumento`
já preenchido com o texto real daquele documento — não uma folha em branco.
É este módulo que traduz o gerador em texto com `{{variáveis}}`.

Por que não é gerado automaticamente a partir do gerador: os geradores montam
o PDF em chamadas de layout (`pdf.paragrafo(...)`, `pdf.cell(...)`, negrito,
tabelas), então não existe "o texto" para extrair — existe uma sequência de
desenho. O que dá para reaproveitar sem duplicar é o que já está em constante:
as cláusulas do acordo de confidencialidade e a lista de direitos do
informativo INFRAERO vêm de `fichas.py`, não de cópia.

**Este texto NÃO afeta o documento oficial.** O gerador continua produzindo o
PDF assinado exatamente como antes (o hash do ato depende disso). O que sai
daqui é matéria-prima para o RH adaptar num modelo próprio.

Ao acrescentar um documento de texto novo ao catálogo, acrescente o corpo aqui
— `tests/test_documentos_catalogo.py` cobra os dois lados.
"""

from __future__ import annotations

# Variáveis do `VARIAVEIS_MODELO` (fichas.py) que fazem sentido em cada texto.
# Só usamos as que já existem: inventar variável aqui geraria um modelo que
# imprime "{{rg}}" cru, porque o contexto não a conhece.


def _acordo_confidencialidade() -> str:
    """Reaproveita as cláusulas de `fichas._ACORDO_CLAUSULAS` (fonte única)."""
    from app.services.fichas import (EMPRESA_CNPJ, EMPRESA_ENDERECO,
                                     _ACORDO_CLAUSULAS)

    partes = [
        # CNPJ e endereço vêm das constantes da marca, não como lacuna para o
        # RH preencher à mão: o sistema já sabe esses dados.
        f"{{{{empresa}}}}, inscrita no CNPJ/MF sob o nº {EMPRESA_CNPJ}, com sede na "
        f"{EMPRESA_ENDERECO}, neste ato representada na forma de seu ato "
        'constitutivo, doravante denominada simplesmente "TRANSMISSORA"; e '
        "{{nome}}, inscrito(a) no CPF sob o nº {{cpf}}, na função de {{cargo}}, "
        'doravante denominado(a) simplesmente "RECEPTORA".',
        "As partes acima qualificadas resolvem celebrar o presente ACORDO DE "
        "CONFIDENCIALIDADE, que se regerá pelas cláusulas seguintes:",
    ]
    for titulo, paragrafos in _ACORDO_CLAUSULAS:
        partes.append(f"{titulo}")
        partes.extend(paragrafos)
    partes.append("Brasília - DF, {{data}}.")
    return "\n\n".join(partes)


def _termo_lgpd_infraero() -> str:
    return "\n\n".join([
        "TERMO DE CONSENTIMENTO PARA TRATAMENTO DE DADOS PESSOAIS",
        "SISTEMA DE CREDENCIAMENTO",
        "Eu, {{nome}}, CPF {{cpf}}, AUTORIZO, de forma livre, informada e "
        "inequívoca, o tratamento dos meus dados pessoais contidos no formulário "
        "de solicitação de credenciais e em sua documentação anexa, em "
        "conformidade com a Lei nº 13.709/2018 - Lei Geral de Proteção de Dados "
        "Pessoais (LGPD).",
        "Brasília - DF, {{data}}.",
    ])


def _informacoes_trabalhador() -> str:
    """Importa a lista REAL de `fichas.DIREITOS_TRABALHADOR` (fonte única).

    A primeira versão deste texto foi escrita à mão e o fiscal barrou a
    entrega: os percentuais que dão valor jurídico ao documento (6% do VT, 8%
    do FGTS, salário até o 5º dia útil) tinham sumido, e entraram itens que o
    documento oficial não tem. Num informativo de direitos trabalhistas ligado
    a contrato com órgão público, isso é grave — e silencioso, porque o texto
    inventado era plausível.
    """
    from app.services.fichas import DIREITOS_TRABALHADOR

    return "\n\n".join([
        "INFORMAÇÕES AO TRABALHADOR",
        "1. {{empresa}} vem, por meio deste, prestar informações ao trabalhador "
        "{{nome}}, {{cargo}}, alocado no contrato {{contrato}}.",
        "2. A GREEN HOUSE informa que os trabalhadores desta empresa possuem "
        "direitos garantidos pela Constituição Federal, pela Consolidação das "
        "Leis Trabalhistas (CLT) e pelas Convenções/Acordos Coletivos de "
        "Trabalho. Assim, listamos abaixo alguns desses direitos:",
        *DIREITOS_TRABALHADOR,
        "3. Informa, ainda, que a Infraero disponibiliza aos trabalhadores de "
        "empresas contratadas um canal para registro de reclamações (Ouvidoria "
        "Interna) relativas às questões trabalhistas decorrentes da prestação "
        "de seus serviços: terceirizados@infraero.gov.br",
        "Brasília - DF, {{data}}.",
    ])


_CORPOS = {
    "acordo_confidencialidade": _acordo_confidencialidade,
    "termo_lgpd_infraero": _termo_lgpd_infraero,
    "informacoes_trabalhador": _informacoes_trabalhador,
}


def corpo_editavel(chave: str) -> str:
    """Texto de partida do modelo criado a partir do documento `chave`."""
    fabrica = _CORPOS.get(chave)
    if fabrica is None:
        raise KeyError(f"'{chave}' não tem corpo editável definido")
    return fabrica()


def tem_corpo(chave: str) -> bool:
    return chave in _CORPOS
