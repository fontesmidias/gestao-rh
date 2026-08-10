"""Catálogo de permissões e papéis do painel (v2.86).

Até aqui `requer_rh` respondia UMA pergunta — *"está logado?"* — e era a única
porta de 476 rotas. Quem entrasse no painel podia efetivar colaborador, desligar
em lote, exportar a base inteira com CPF, baixar a trilha de auditoria e **criar
outro usuário administrador**. Não havia degrau nenhum entre "consultar a lista
de candidatos" e "apagar a pessoa".

Isso passou a doer agora porque os módulos de Processos e Recepção trazem para
dentro do sistema gente que **não é do RH** — o gestor que avalia a própria
equipe, a recepcionista que anuncia visita. Dar a essas pessoas a chave que o
Coordenador tem hoje não é opção.

Três decisões que sustentam o desenho, e que NÃO devem ser afrouxadas:

1. **A permissão é declarada na ROTA, nunca no módulo.** Módulo é pasta; papel é
   gente. `colaboradores.py` tem, sob o MESMO router, o `GET` que lista e o
   `POST .../desligar` — permissão por módulo daria a quem consulta o poder de
   desligar. Ver `PERMISSOES` abaixo: o eixo é a NATUREZA DO ATO.

2. **Rota sem permissão declarada é REPROVADA no CI**, não liberada por padrão.
   Se o default fosse "aberto", "ainda não declarei" e "decidi que é livre"
   ficariam indistinguíveis no código — e a diferença só apareceria no dia em
   que alguém achasse a rota. É a família do defeito silencioso que este projeto
   já pagou caro: o worker que não roda (v2.66), o documento que não nasce
   (v2.69), a lixeira de mão única (v2.72.2). O teste
   `test_permissoes_declaradas.py` varre `app/api/` e falha NOMEANDO a órfã.

3. **O superadmin não é um papel com todas as permissões marcadas — ele IGNORA
   a checagem** (ver `pode`). A diferença aparece no dia em que um módulo novo
   registra uma permissão nova: se fosse lista marcada, a permissão nasceria
   DESMARCADA para o superadmin e o dono do sistema descobriria isso levando um
   403 na própria casa. Módulo novo nasce 100% liberado ao superadmin porque a
   checagem dele não consulta lista nenhuma.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Catálogo de permissões
# ---------------------------------------------------------------------------
#
# O eixo é a NATUREZA DO ATO, não o arquivo onde a rota mora. "Ler a ficha de
# alguém" e "desligar a pessoa" são coisas diferentes ainda que vizinhas no
# mesmo `.py`; "exportar a base com 1.171 CPFs" é diferente das duas, mesmo
# sendo um GET.
#
# `perigosa=True` marca o que não se desfaz sozinho — o front pinta diferente e
# a tela de papéis avisa antes de marcar. Não é decorativo: é o que impede
# alguém liberar `colaboradores:desligar` achando que libera uma consulta.


@dataclass(frozen=True)
class Permissao:
    chave: str
    rotulo: str
    grupo: str
    descricao: str
    perigosa: bool = False


def _p(chave: str, rotulo: str, grupo: str, descricao: str,
       perigosa: bool = False) -> Permissao:
    return Permissao(chave, rotulo, grupo, descricao, perigosa)


PERMISSOES: tuple[Permissao, ...] = (
    # --- Admissão ---------------------------------------------------------
    _p("admissao:ler", "Ver admissões", "Admissão",
       "Consultar a lista de candidatos em admissão e abrir a ficha."),
    _p("admissao:escrever", "Editar admissões", "Admissão",
       "Convidar candidato, corrigir dados da ficha e reenviar link."),
    _p("admissao:revisar_documento", "Aprovar/reprovar documentos", "Admissão",
       "Aprovar, rejeitar ou dispensar documento enviado — inclusive em lote."),
    _p("admissao:dossie", "Gerar e baixar dossiê", "Admissão",
       "Montar o dossiê da pessoa. Reúne num PDF só tudo que ela enviou."),

    # --- Colaboradores ----------------------------------------------------
    _p("colaboradores:ler", "Ver colaboradores", "Colaboradores",
       "Consultar a base de colaboradores ativos e desligados."),
    _p("colaboradores:escrever", "Editar colaboradores", "Colaboradores",
       "Corrigir cadastro, lotação, jornada e vínculos."),
    _p("colaboradores:efetivar", "Efetivar como colaborador", "Colaboradores",
       "Transformar candidato aprovado em colaborador da base.", perigosa=True),
    _p("colaboradores:desligar", "Desligar colaborador", "Colaboradores",
       "Registrar o desligamento. Encerra benefícios ativos, como o creche.",
       perigosa=True),
    _p("colaboradores:reverter", "Reverter para candidato", "Colaboradores",
       "Devolver colaborador ao fluxo de admissão. Exige motivo.", perigosa=True),
    _p("colaboradores:matricula", "Trocar matrícula", "Colaboradores",
       "Alterar a matrícula. É a chave que liga a pessoa ao ponto do Tirvu.",
       perigosa=True),

    # --- Dado pessoal em massa -------------------------------------------
    #
    # Separado do resto de propósito. Um GET que devolve a base inteira com CPF
    # não é "leitura" no mesmo sentido que abrir a ficha de uma pessoa: é
    # extração de dado pessoal para fora do sistema, e é assim que a LGPD o vê.
    _p("dados:exportar_base", "Exportar base de pessoas", "Dados pessoais",
       "Baixar planilhas com a base (Tirvu, Dexion, creche). Leva CPF de todos.",
       perigosa=True),
    _p("dados:arquivo_lote", "Baixar dossiês em lote", "Dados pessoais",
       "Baixar de uma vez os documentos de várias pessoas (até 500).",
       perigosa=True),
    _p("dados:auditoria", "Ver trilha de auditoria", "Dados pessoais",
       "Consultar quem fez o quê no sistema."),
    _p("dados:logs", "Ver e baixar logs", "Dados pessoais",
       "Registros técnicos dos serviços. Contêm nome e e-mail de gente real.",
       perigosa=True),
    _p("dados:expurgar", "Expurgar dados", "Dados pessoais",
       "Apagar telemetria antiga em definitivo. Não passa pela lixeira.",
       perigosa=True),

    # --- Creche -----------------------------------------------------------
    _p("creche:ler", "Ver reembolso-creche", "Creche",
       "Consultar levantamentos, crianças e documentos do benefício."),
    _p("creche:decidir", "Decidir sobre o benefício", "Creche",
       "Deferir, indeferir, devolver, suspender ou encerrar. Mexe em folha.",
       perigosa=True),

    # --- Seleção ----------------------------------------------------------
    _p("selecao:ler", "Ver talentos e vagas", "Seleção",
       "Banco de talentos, vagas, currículos e ranking de aderência."),
    _p("selecao:escrever", "Gerir talentos e vagas", "Seleção",
       "Cadastrar vaga, anotar no CRM, arquivar talento e enviar teste."),
    _p("selecao:entrevistar", "Conduzir entrevistas", "Seleção",
       "Marcar, preencher e assinar ficha de entrevista e triagem."),
    _p("selecao:provas", "Montar provas", "Seleção",
       "Criar provas e banco de itens. Dá acesso ao gabarito."),
    _p("selecao:corrigir", "Corrigir provas", "Seleção",
       "Pontuar questões discursivas e fechar nota."),

    # --- Desenvolvimento e desempenho ------------------------------------
    _p("desenvolvimento:ler", "Ver desenvolvimento", "Desenvolvimento",
       "Cursos, certificações e reciclagens dos colaboradores."),
    _p("desenvolvimento:validar", "Validar certificados", "Desenvolvimento",
       "Aprovar, devolver ou recusar certificado. Define a validade."),
    _p("desempenho:ler", "Ver desempenho", "Desempenho",
       "Ciclos, avaliações e fatos observados."),
    _p("desempenho:avaliar", "Avaliar equipe", "Desempenho",
       "Preencher avaliação e registrar fato observado sobre a equipe."),
    _p("desempenho:homologar", "Homologar avaliações", "Desempenho",
       "Fechar a avaliação depois do feedback e da manifestação.",
       perigosa=True),

    # --- Organização ------------------------------------------------------
    _p("organizacao:ler", "Ver postos e jornadas", "Organização",
       "Postos de serviço, jornadas, cargos e empresas."),
    _p("organizacao:escrever", "Gerir postos e jornadas", "Organização",
       "Criar e editar posto, jornada, cargo e a integração com o Tirvu."),

    # --- Documentos e assinaturas ----------------------------------------
    _p("documentos:modelos", "Gerir modelos de documento", "Documentos",
       "Criar e editar modelos que a pessoa assina."),
    _p("documentos:assinar", "Assinar pela empresa", "Documentos",
       "Assinar documento como representante. É ato de vontade, não carimbo.",
       perigosa=True),
    _p("documentos:minutario", "Usar o minutário", "Documentos",
       "Modelos de mensagem e composição assistida por IA."),

    # --- Recepção (módulo novo) ------------------------------------------
    _p("recepcao:anunciar", "Anunciar visita", "Recepção",
       "Registrar quem chegou e avisar os responsáveis pelo assunto."),
    _p("recepcao:configurar", "Configurar a recepção", "Recepção",
       "Assuntos, tags e quem é da sede."),

    # --- Processos (módulo novo) -----------------------------------------
    _p("processos:ler", "Ver a carteira de processos", "Processos",
       "Consultar processos, titulares e cadeia de substituição."),
    _p("processos:escrever", "Gerir a carteira de processos", "Processos",
       "Criar processo, trocar titular, redistribuir e dimensionar a equipe."),

    # --- Administração do sistema ----------------------------------------
    _p("config:ler", "Ver configurações", "Sistema",
       "Consultar as configurações do sistema."),
    _p("config:escrever", "Alterar configurações", "Sistema",
       "Integrações, e-mail, IA, marca, avisos e retenções."),
    _p("config:usuarios", "Gerir usuários e papéis", "Sistema",
       "Criar usuário, definir papel e redefinir senha de terceiros.",
       perigosa=True),
    _p("sistema:lixeira", "Usar a lixeira", "Sistema",
       "Ver e restaurar o que foi excluído."),
    _p("sistema:telemetria", "Ver telemetria", "Sistema",
       "Como as pessoas usam o sistema, erros e alertas."),
)

POR_CHAVE: dict[str, Permissao] = {p.chave: p for p in PERMISSOES}
CHAVES: frozenset[str] = frozenset(POR_CHAVE)


# ---------------------------------------------------------------------------
# Papéis
# ---------------------------------------------------------------------------
#
# Os papéis abaixo são o PADRÃO DE FÁBRICA — o ponto de partida de uma
# instalação, não a palavra final. O superadmin edita cada um pelo painel, e o
# que ele escolher fica no banco (`Papel.permissoes`); estas listas voltam a
# valer só para papel que ele nunca tocou.
#
# É a mesma cascata das exigências da v2.80 — fábrica → casa → exceção — e pelo
# mesmo motivo: se o padrão morasse no banco desde o início, um módulo novo
# nasceria invisível para todo mundo, e ninguém saberia que precisava marcar.


PAPEL_SUPERADMIN = "superadmin"


@dataclass(frozen=True)
class PapelPadrao:
    chave: str
    rotulo: str
    descricao: str
    permissoes: frozenset[str] = field(default_factory=frozenset)
    tudo: bool = False


def _todas_menos(*excluir: str) -> frozenset[str]:
    return frozenset(CHAVES - set(excluir))


PAPEIS_PADRAO: tuple[PapelPadrao, ...] = (
    PapelPadrao(
        PAPEL_SUPERADMIN, "Superadministrador",
        "Dono do sistema. Faz tudo, inclusive definir o que cada papel pode. "
        "Módulo novo já nasce liberado para ele.",
        tudo=True,
    ),
    PapelPadrao(
        "admin", "Administrador",
        "Administra o sistema no dia a dia, sem mexer em usuários e papéis.",
        # A exceção é deliberada: quem administra o sistema não escolhe quem
        # entra nele. Sem esse degrau, "admin" e "superadmin" seriam o mesmo
        # papel com dois nomes — e o segundo poderia se promover ao primeiro.
        permissoes=_todas_menos("config:usuarios"),
    ),
    PapelPadrao(
        "rh", "RH",
        "Equipe de RH. Conduz admissão, colaboradores, benefícios e seleção.",
        permissoes=frozenset({
            "admissao:ler", "admissao:escrever", "admissao:revisar_documento",
            "admissao:dossie",
            "colaboradores:ler", "colaboradores:escrever",
            "colaboradores:efetivar", "colaboradores:desligar",
            "creche:ler", "creche:decidir",
            "selecao:ler", "selecao:escrever", "selecao:entrevistar",
            "selecao:provas", "selecao:corrigir",
            "desenvolvimento:ler", "desenvolvimento:validar",
            "desempenho:ler", "desempenho:avaliar",
            "organizacao:ler", "organizacao:escrever",
            "documentos:modelos", "documentos:minutario",
            "processos:ler",
            "sistema:lixeira", "config:ler",
            "dados:auditoria",
        }),
    ),
    PapelPadrao(
        "gestor", "Gestor de equipe",
        "Não é do RH. Avalia os próprios colaboradores e acompanha a equipe.",
        # Sem `colaboradores:escrever` e sem nada de admissão: o gestor olha a
        # equipe dele, não opera o cadastro. `desempenho:homologar` fica de fora
        # porque homologar é o ato que fecha a avaliação — quem avalia não
        # deveria também dar a palavra final sobre a própria avaliação.
        permissoes=frozenset({
            "colaboradores:ler",
            "desempenho:ler", "desempenho:avaliar",
            "desenvolvimento:ler",
            "processos:ler",
        }),
    ),
    PapelPadrao(
        "recepcao", "Recepção",
        "Anuncia visitas e encaminha assuntos aos responsáveis.",
        # Deliberadamente estreito: a recepção precisa achar a pessoa certa,
        # não ver a ficha dela. `colaboradores:ler` NÃO entra — o seletor da
        # recepção lê só quem foi marcado como da sede, por rota própria.
        permissoes=frozenset({"recepcao:anunciar", "processos:ler"}),
    ),
)

PAPEIS_POR_CHAVE: dict[str, PapelPadrao] = {p.chave: p for p in PAPEIS_PADRAO}


def permissoes_padrao(papel: str) -> frozenset[str]:
    """Permissões de fábrica de um papel. Papel desconhecido não recebe nada."""
    padrao = PAPEIS_POR_CHAVE.get(papel)
    if padrao is None:
        return frozenset()
    return CHAVES if padrao.tudo else padrao.permissoes


def pode(papel: str, concedidas: set[str] | frozenset[str] | None,
         permissao: str) -> bool:
    """Responde se um papel com estas permissões pode fazer `permissao`.

    O superadmin passa SEM consultar lista — é o que faz módulo novo nascer
    liberado para ele sem ninguém precisar lembrar de marcar a caixa. Ver a
    decisão 3 no topo do arquivo.
    """
    if papel == PAPEL_SUPERADMIN:
        return True
    if permissao not in CHAVES:
        # Permissão fora do catálogo é erro de programação, não negativa de
        # acesso: devolver `False` calado faria a rota responder 403 para todo
        # mundo e alguém procuraria o defeito no papel do usuário.
        raise KeyError(f"permissao_desconhecida: {permissao}")
    return permissao in (concedidas or frozenset())


def validar_chaves(chaves: list[str] | set[str]) -> list[str]:
    """Devolve, ordenadas, as chaves válidas — recusando as de fora do catálogo.

    Usada na rota que salva um papel. Aceitar chave desconhecida deixaria o
    banco guardar permissão que nada concede: a tela mostraria a caixa marcada
    e o acesso continuaria negado, sem ninguém entender por quê.
    """
    desconhecidas = sorted(set(chaves) - CHAVES)
    if desconhecidas:
        raise ValueError(f"permissoes_desconhecidas: {', '.join(desconhecidas)}")
    return sorted(set(chaves))


def catalogo_para_front() -> list[dict]:
    """Catálogo agrupado, na ordem em que os grupos aparecem em `PERMISSOES`."""
    grupos: list[dict] = []
    indice: dict[str, dict] = {}
    for p in PERMISSOES:
        grupo = indice.get(p.grupo)
        if grupo is None:
            grupo = {"grupo": p.grupo, "permissoes": []}
            indice[p.grupo] = grupo
            grupos.append(grupo)
        grupo["permissoes"].append({
            "chave": p.chave, "rotulo": p.rotulo,
            "descricao": p.descricao, "perigosa": p.perigosa,
        })
    return grupos
