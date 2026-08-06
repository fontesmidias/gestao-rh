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


class Origem(str, enum.Enum):
    """De onde o documento vem — e, portanto, o que a amostra precisa (v2.67).

    Existe porque o catálogo nasceu candidato-cêntrico: todo gerador tem a
    assinatura `(db, candidato)` e a prévia monta um `Candidato` fictício. Os
    documentos do Módulo de Entrevistas não recebem candidato — recebem uma
    ENTREVISTA ou um ROTEIRO —, e forçá-los naquele molde exigiria uma das duas
    saídas ruins:

    - **acrescentar valores ao `DocumentoAssinavel`**, que é pior do que parece:
      `api/rh_ficha.py:38` faz `_TODOS = list(DocumentoAssinavel)` e usa a lista
      em `DOCS_POR_SECAO`, então editar os dados pessoais de alguém passaria a
      **invalidar a ficha de entrevista**; e `_docs_exigidos` faria a ficha
      virar pendência de assinatura do candidato no wizard;
    - **deixar os documentos fora do catálogo**, que é justamente o que o Bruno
      cobrou (*"a cada documento novo gerado, ele deve compor o módulo de
      documentos também"*).

    Então o catálogo passou a ter DUAS famílias. `_conferir_catalogo` continua
    cobrando a cobertura EXATA do enum — só que da família `admissao`.
    """
    admissao = "admissao"        # os 11 que o enum `DocumentoAssinavel` cobre
    entrevista = "entrevista"    # v2.67: ficha, triagem e roteiro


@dataclass(frozen=True)
class DocumentoSistema:
    chave: str                 # valor do DocumentoAssinavel (família admissão)
    rotulo: str                # nome legível (espelha NOMES_DOC)
    quando: str                # em que situação o sistema gera este documento
    grupo: str                 # agrupa os cards na tela
    formato: Formato
    # Por que não é duplicável (só para formulario/hibrido) — a tela mostra.
    porque_nao_duplica: str = ""
    base: bool = False         # exigido de todo candidato
    origem: Origem = Origem.admissao
    # Só para a família entrevista: onde o documento VIVE (§ 15.4). A tela
    # mostra este texto, e ele diz explicitamente que a ficha não vai ao dossiê
    # — quem lê a tela precisa saber disso sem abrir o código.
    onde_vive: str = ""


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
    # Uma ficha de integração por regime; o candidato recebe exatamente uma. O
    # corpo é o mesmo e o que muda são os PERÍODOS DE PAGAMENTO dos benefícios.
    _d(chave="informativo_intermitente", grupo="Ficha de integração",
       rotulo="Informativo de Integração — Intermitente",
       quando="Gerado quando o regime é intermitente; só vai ao candidato "
              "depois que o RH libera o informativo. Benefícios apurados "
              "SEMANALMENTE.",
       formato=Formato.hibrido,
       porque_nao_duplica="Começa com um bloco de dados em tabela (banco, PIX, "
                          "posto) e só depois vem o texto das orientações."),

    _d(chave="informativo_efetivo", grupo="Ficha de integração",
       rotulo="Informativo de Integração — Efetivo",
       quando="Gerado quando o regime é efetivo (o padrão); só vai ao candidato "
              "depois que o RH libera o informativo. Benefícios apurados do dia "
              "1 ao dia 30 do mês.",
       formato=Formato.hibrido,
       porque_nao_duplica="Mesma estrutura da versão do intermitente: bloco de "
                          "dados em tabela (banco, PIX, posto) antes do texto "
                          "das orientações."),

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

# ---------------------------------------------------------------------------
# Família ENTREVISTA (v2.67, § 15.2)
#
# O Bruno cobrou a regra da v2.21 — *"a cada documento novo gerado, ele deve
# compor o módulo de documentos também e todas as funcionalidades herdadas"* —
# e ela estava sendo cumprida pela metade: a v2.66 pôs os três E-MAILS do módulo
# no catálogo de e-mails e **nenhum** dos documentos aqui. Documento gerado sem
# entrada no catálogo é documento que o RH não consegue ver nem conferir.
#
# Nenhum deles é duplicável: os três montam estrutura (notas com âncora,
# perguntas em tabela, escala) a partir de dados que não existem em
# `VARIAVEIS_MODELO` — uma cópia em texto sairia sem justamente o que dá função
# ao documento. É a mesma razão da `autodeclaracao_residencia`.
# ---------------------------------------------------------------------------

CATALOGO_ENTREVISTAS: tuple[DocumentoSistema, ...] = (
    _d(chave="entrevista_ficha", grupo="Entrevistas", origem=Origem.entrevista,
       rotulo="Ficha de Entrevista preenchida",
       quando="Gerada a partir de uma entrevista REALIZADA e completa. "
              "Assinável pelo RH que conduziu, com a senha da própria sessão.",
       formato=Formato.hibrido,
       onde_vive="Fica no Arquivo e na ficha da pessoa. NÃO entra no dossiê de "
                 "admissão: o dossiê circula (cliente, pasta física), e nota de "
                 "seleção com justificativa é dado sensível sobre a pessoa.",
       porque_nao_duplica="Cada competência imprime a nota, a âncora exata "
                          "daquela nota e a justificativa escrita — estrutura "
                          "que varia por roteiro e por entrevista. Um texto com "
                          "variáveis perderia a âncora, que é o que faz a nota "
                          "significar algo."),

    _d(chave="entrevista_triagem", grupo="Entrevistas", origem=Origem.entrevista,
       rotulo="Ficha de Triagem preenchida",
       quando="Gerada a partir de uma triagem realizada, com desfecho "
              "registrado. Fecha o histórico da pessoa.",
       formato=Formato.formulario,
       onde_vive="Fica no Arquivo e na ficha da pessoa. NÃO entra no dossiê de "
                 "admissão.",
       porque_nao_duplica="É um formulário: uma linha por pergunta do roteiro "
                          "de triagem vigente, e o roteiro é editável pelo RH. "
                          "Um texto fixo congelaria as perguntas de hoje."),

    _d(chave="entrevista_roteiro", grupo="Entrevistas", origem=Origem.entrevista,
       rotulo="Roteiro de Entrevista publicado",
       quando="Gerado a partir de um roteiro PUBLICADO (rascunho não gera). "
              "É a prova de que o roteiro foi aprovado ANTES de ser usado.",
       formato=Formato.hibrido,
       onde_vive="Fica em Configurações → Roteiros de entrevista e no Arquivo. "
                 "É documento da EMPRESA, não da pessoa — não se anexa a "
                 "ninguém.",
       porque_nao_duplica="Traz a escala e, por competência, as quatro âncoras "
                          "e as duas variantes de pergunta, em tabela. Quem "
                          "quiser um roteiro diferente duplica o ROTEIRO na "
                          "tela de roteiros, que é editável — copiar o texto do "
                          "PDF não criaria um roteiro utilizável."),
)

# Tudo junto, para a tela. A ORDEM importa: admissão primeiro, entrevistas
# depois — o RH abre esta tela procurando os documentos da admissão.
TODOS: tuple[DocumentoSistema, ...] = CATALOGO + CATALOGO_ENTREVISTAS

CATALOGO_POR_CHAVE = {d.chave: d for d in TODOS}


def documento(chave: str) -> DocumentoSistema:
    d = CATALOGO_POR_CHAVE.get(chave)
    if d is None:
        raise KeyError(f"documento '{chave}' não está no catálogo")
    return d


def duplicavel(chave: str) -> bool:
    """Só texto corrido vira modelo editável (ver o cabeçalho do módulo)."""
    return documento(chave).formato is Formato.texto


def da_entrevista(chave: str) -> bool:
    """A prévia deste documento precisa de entrevista/roteiro, não de candidato."""
    return documento(chave).origem is Origem.entrevista


def listar() -> list[dict]:
    """Catálogo para a tela do RH."""
    return [{
        "chave": d.chave, "rotulo": d.rotulo, "grupo": d.grupo,
        "quando": d.quando, "formato": d.formato.value,
        "base": d.base, "duplicavel": d.formato is Formato.texto,
        "porque_nao_duplica": d.porque_nao_duplica,
        "origem": d.origem.value, "onde_vive": d.onde_vive,
    } for d in TODOS]


def _conferir_catalogo() -> None:
    """O catálogo tem que cobrir o enum inteiro — nem a mais, nem a menos.

    Documento novo no `DocumentoAssinavel` sem entrada aqui sumiria da tela do
    RH sem ninguém perceber; entrada aqui sem enum correspondente geraria 404
    ao pedir o preview.

    A cobrança do ENUM vale para a família `admissao`, que é a que ele descreve.
    A família `entrevista` (v2.67) não tem — e não deve ter — valor no
    `DocumentoAssinavel`: ver o docstring de `Origem` para o estrago que isso
    causaria em `rh_ficha.py` e no wizard. Ela é cobrada pelas regras próprias
    logo abaixo.
    """
    do_enum = {d.value for d in DocumentoAssinavel}
    da_admissao = {d.chave for d in CATALOGO}
    if faltando := do_enum - da_admissao:
        raise RuntimeError(f"documentos fora do catálogo: {sorted(faltando)}")
    if sobrando := da_admissao - do_enum:
        raise RuntimeError(f"catálogo cita documento inexistente: {sorted(sobrando)}")
    for d in CATALOGO:
        esperado = DocumentoAssinavel(d.chave) in FICHAS_BASE
        if d.base != esperado:
            raise RuntimeError(f"'{d.chave}': `base` diverge de FICHAS_BASE")
    for d in TODOS:
        if d.formato is not Formato.texto and not d.porque_nao_duplica:
            raise RuntimeError(f"'{d.chave}': precisa explicar por que não duplica")

    # A família entrevista NÃO pode encostar no enum das assinaturas do
    # candidato. Se alguém "resolver" um 404 acrescentando `entrevista_ficha` ao
    # `DocumentoAssinavel`, o sistema para AQUI, no import — em vez de o defeito
    # aparecer como uma ficha de entrevista cobrada do candidato no wizard.
    for d in CATALOGO_ENTREVISTAS:
        if d.origem is not Origem.entrevista:
            raise RuntimeError(f"'{d.chave}': família entrevista com origem errada")
        if d.chave in do_enum:
            raise RuntimeError(
                f"'{d.chave}' virou valor de DocumentoAssinavel — isso o tornaria "
                "documento exigível do candidato no wizard e faria a edição da "
                "ficha invalidá-lo (rh_ficha.py::DOCS_POR_SECAO). Ver Origem.")
        if d.base:
            raise RuntimeError(f"'{d.chave}': documento de entrevista não é ficha base")
        # Chave repetida entre as famílias faria uma sombrear a outra no
        # `CATALOGO_POR_CHAVE`, servindo a prévia errada em silêncio.
        if d.chave in da_admissao:
            raise RuntimeError(f"'{d.chave}': chave duplicada entre as famílias")
        if not d.onde_vive:
            raise RuntimeError(
                f"'{d.chave}': precisa dizer ONDE VIVE — o § 15.4 depende de a "
                "tela afirmar que a ficha não vai ao dossiê")


_conferir_catalogo()
