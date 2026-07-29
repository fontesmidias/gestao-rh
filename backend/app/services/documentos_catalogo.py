"""Catálogo dos DOCUMENTOS do sistema, nos moldes do catálogo de e-mails.

Pedido do Bruno (2026-07-28, madrugada): "para o módulo de modelos de
documentos, faça aos moldes dos modelos de e-mails. Pegue todos os que já
temos disponíveis no sistema do tipo hardcoded e coloque-os lá para CRUD e
boas práticas, para que possamos duplicar e outras coisas mais, bem como
preview decente e que também possamos baixar."

O que este arquivo faz — e o que deliberadamente NÃO faz
--------------------------------------------------------
Ele dá ao RH a visão única que faltava: **todos os documentos que o sistema
gera**, com preview em PDF, download e — nos que são texto corrido — o botão
para criar um MODELO EDITÁVEL a partir do conteúdo real.

O que ele **não** faz é substituir os geradores por template. Dois motivos, e
o primeiro é intransponível:

1. **O hash do ato de assinatura é calculado sobre o PDF gerado**
   (`assinaturas.py`, assinatura em lote: gera o PDF sem bloco, tira o
   SHA-256, depois gera o assinado). Trocar o gerador por um template faria o
   mesmo documento produzir outro hash — e todo manifesto já emitido aponta
   para um hash que deixaria de se reproduzir. Isso é a prova de autenticidade
   do que as pessoas assinaram.
2. **Metade deles não é texto.** `ficha_cadastro` tem 49 chamadas de campo,
   loop de dependentes e loop de adicionais; `ficha_emergencia` itera
   contatos; `ficha_cadastral_terceirizado` é réplica de formulário oficial.
   Formulário estruturado não cabe em template de substituição — a tentativa
   sairia com o layout destruído.

Daí a classificação de cada documento em `Formato`, que a tela usa para dizer
ao RH o que dá para fazer com cada um. Duplicar um documento de texto cria uma
CÓPIA editável (`ModeloDocumento`); o original segue intacto, gerando os PDFs
oficiais como sempre.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.models.assinatura import FICHAS_BASE, DocumentoAssinavel


class Formato(str, enum.Enum):
    """Como o documento é montado — decide o que a tela oferece."""

    # Texto corrido com variáveis: dá para copiar para um modelo editável.
    texto = "texto"
    # Formulário com rótulo/valor, tabelas e loops de dados da ficha.
    formulario = "formulario"
    # Texto + um trecho estruturado (branch ou tabela) que o modelo não faz.
    hibrido = "hibrido"


@dataclass(frozen=True)
class DocumentoSistema:
    chave: str                 # valor do DocumentoAssinavel
    rotulo: str                # nome legível (espelha NOMES_DOC)
    quando: str                # em que situação o sistema gera este documento
    grupo: str                 # agrupa os cards na tela
    formato: Formato
    # Por que não é duplicável (só para formulario/hibrido) — a tela mostra.
    porque_nao_duplica: str = ""
    base: bool = False         # exigido de todo candidato


def _d(**kw) -> DocumentoSistema:
    return DocumentoSistema(**kw)


CATALOGO: tuple[DocumentoSistema, ...] = (
    # ------------------------------------------------ fichas de todo candidato
    _d(chave="ficha_cadastro", base=True, grupo="Admissão (todo candidato)",
       rotulo="Ficha Cadastral do Colaborador",
       quando="Gerada para todo candidato; assinada no wizard da admissão.",
       formato=Formato.formulario,
       porque_nao_duplica="É um formulário: dezenas de campos em tabela, mais a "
                          "lista de dependentes e a de adicionais, que variam de "
                          "pessoa para pessoa. Não cabe em um texto com variáveis."),

    _d(chave="ficha_emergencia", base=True, grupo="Admissão (todo candidato)",
       rotulo="Ficha de Emergência do Colaborador",
       quando="Gerada para todo candidato; assinada no wizard da admissão.",
       formato=Formato.formulario,
       porque_nao_duplica="É um formulário e repete uma seção por contato de "
                          "emergência cadastrado."),

    _d(chave="termo_vt", base=True, grupo="Admissão (todo candidato)",
       rotulo="Termo de Opção pelo Vale-Transporte",
       quando="Gerado para todo candidato; o texto muda conforme ele opta ou "
              "não pelo VT.",
       formato=Formato.hibrido,
       porque_nao_duplica="O texto tem dois caminhos (opta / não opta) e uma "
                          "seção com os dados do trajeto que só aparece para quem "
                          "opta."),

    _d(chave="acordo_confidencialidade", base=True, grupo="Admissão (todo candidato)",
       rotulo="Acordo de Confidencialidade",
       quando="Gerado para todo candidato; vale retroativamente desde 2026-07-16.",
       formato=Formato.texto),

    # ---------------------------------------------------------- posto INFRAERO
    _d(chave="oficio_cartao_cidadao", grupo="Posto INFRAERO",
       rotulo="Ofício INFRAERO — Cartão Cidadão e extrato do INSS",
       quando="Gerado quando o candidato é alocado em posto INFRAERO.",
       formato=Formato.hibrido,
       porque_nao_duplica="Tem uma tabela de Nome/Cargo/Assinatura desenhada no "
                          "PDF, que um texto com variáveis não reproduz."),

    _d(chave="informacoes_trabalhador", grupo="Posto INFRAERO",
       rotulo="Informações ao Trabalhador (INFRAERO)",
       quando="Gerado no posto INFRAERO; só vai ao candidato depois que o RH "
              "libera o informativo.",
       formato=Formato.texto),

    _d(chave="termo_lgpd_infraero", grupo="Posto INFRAERO",
       rotulo="Termo de Consentimento LGPD — Credenciamento (INFRAERO)",
       quando="Gerado quando o candidato é alocado em posto INFRAERO.",
       formato=Formato.texto),

    # ------------------------------------------------------- kit Presidência
    _d(chave="ficha_cadastral_terceirizado", grupo="Kit Presidência",
       rotulo="Ficha Cadastral de Terceirizado (Presidência)",
       quando="Gerada quando o posto tem o kit da Presidência marcado.",
       formato=Formato.formulario,
       porque_nao_duplica="É a réplica de um formulário oficial: só campos em "
                          "tabela, sem nenhum texto corrido."),

    _d(chave="oficio_apresentacao_presidencia", grupo="Kit Presidência",
       rotulo="Ofício de Apresentação — Presidência da República",
       quando="Gerado quando o posto tem o kit da Presidência marcado.",
       formato=Formato.hibrido,
       porque_nao_duplica="O ofício traz RG, órgão emissor e endereço do "
                          "colaborador, que ainda não existem como variáveis de "
                          "modelo — uma cópia sairia com esses dados faltando, "
                          "e é justamente o que a Presidência exige para o "
                          "credenciamento."),

    # ------------------------------------------------------------- por regime
    _d(chave="informativo_intermitente", grupo="Regime intermitente",
       rotulo="Informativo de Integração — Intermitente",
       quando="Gerado quando o regime é intermitente; só vai ao candidato "
              "depois que o RH libera o informativo.",
       formato=Formato.hibrido,
       porque_nao_duplica="Começa com um bloco de dados em tabela (banco, PIX, "
                          "posto) e só depois vem o texto das orientações."),

    # ------------------------------------------------------------ condicional
    _d(chave="autodeclaracao_residencia", grupo="Conforme a ficha",
       rotulo="Autodeclaração de Residência",
       quando="Gerada quando o candidato informa que o comprovante de endereço "
              "está em nome de outra pessoa.",
       formato=Formato.hibrido,
       porque_nao_duplica="A declaração nomeia o titular do comprovante, o "
                          "vínculo com ele e o endereço — dados que ainda não "
                          "existem como variáveis de modelo. Sem eles a cópia "
                          "perderia justamente o que dá função ao documento."),
)

CATALOGO_POR_CHAVE = {d.chave: d for d in CATALOGO}


def documento(chave: str) -> DocumentoSistema:
    d = CATALOGO_POR_CHAVE.get(chave)
    if d is None:
        raise KeyError(f"documento '{chave}' não está no catálogo")
    return d


def duplicavel(chave: str) -> bool:
    """Só texto corrido vira modelo editável (ver o cabeçalho do módulo)."""
    return documento(chave).formato is Formato.texto


def listar() -> list[dict]:
    """Catálogo para a tela do RH."""
    return [{
        "chave": d.chave, "rotulo": d.rotulo, "grupo": d.grupo,
        "quando": d.quando, "formato": d.formato.value,
        "base": d.base, "duplicavel": d.formato is Formato.texto,
        "porque_nao_duplica": d.porque_nao_duplica,
    } for d in CATALOGO]


def _conferir_catalogo() -> None:
    """O catálogo tem que cobrir o enum inteiro — nem a mais, nem a menos.

    Documento novo no `DocumentoAssinavel` sem entrada aqui sumiria da tela do
    RH sem ninguém perceber; entrada aqui sem enum correspondente geraria 404
    ao pedir o preview.
    """
    do_enum = {d.value for d in DocumentoAssinavel}
    do_catalogo = set(CATALOGO_POR_CHAVE)
    if faltando := do_enum - do_catalogo:
        raise RuntimeError(f"documentos fora do catálogo: {sorted(faltando)}")
    if sobrando := do_catalogo - do_enum:
        raise RuntimeError(f"catálogo cita documento inexistente: {sorted(sobrando)}")
    for d in CATALOGO:
        esperado = DocumentoAssinavel(d.chave) in FICHAS_BASE
        if d.base != esperado:
            raise RuntimeError(f"'{d.chave}': `base` diverge de FICHAS_BASE")
        if d.formato is not Formato.texto and not d.porque_nao_duplica:
            raise RuntimeError(f"'{d.chave}': precisa explicar por que não duplica")


_conferir_catalogo()
