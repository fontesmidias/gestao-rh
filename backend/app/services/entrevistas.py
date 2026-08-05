"""O INSTRUMENTO da entrevista — competências, âncoras, escalas e perguntas.

Vive aqui como **constante de módulo, nunca no banco**, pelo mesmo motivo que a
cartilha do avaliador (`services/desempenho.py`) não está: o front lê de
`GET /rh/entrevistas/formulario` e NÃO duplica nenhum texto. Mudar uma âncora é
mudar este arquivo, e a tela acompanha sozinha.

Três decisões de desenho que sustentam o resto:

1. **Escala 1–4, sem ponto médio** — de propósito. Com 1–5 o avaliador foge
   para o 3 e a nota não diz nada.
2. **Âncora comportamental (BARS)**: cada ponto da escala descreve um
   COMPORTAMENTO OBSERVÁVEL, não um adjetivo. A consequência de produto é a
   `justificativa obrigatória por competência` — nota sem frase ao lado é
   ruído, e `validar_preenchimento` recusa.
3. **Duas variantes da MESMA pergunta** (comportamental × situacional): a
   comportamental ("conte uma vez em que…") exige que a pessoa tenha uma
   história para contar, e não funciona com quem nunca trabalhou formalmente —
   primeiro emprego é fatia real nestes cargos. Nesse caso ela não mediria
   competência, mediria currículo. **A competência, a escala e a âncora são
   idênticas nas duas** — duas portas, mesma sala.

A TRIAGEM não tem nada disso de propósito (§ 4.1 do documento): é checagem de
viabilidade, não avaliação. Ver `PERGUNTAS_TRIAGEM`.
"""

# --------------------------------------------------------------------------
# Escala da entrevista
# --------------------------------------------------------------------------

ESCALA = [
    {"valor": 4, "rotulo": "4 — Evidência forte"},
    {"valor": 3, "rotulo": "3 — Atende"},
    {"valor": 2, "rotulo": "2 — Genérico, sem exemplo"},
    {"valor": 1, "rotulo": "1 — Contraindica"},
]

VALORES_VALIDOS = {e["valor"] for e in ESCALA}


# --------------------------------------------------------------------------
# As 4 competências (§ 4.2). Critério: (a) observável numa conversa de 20 min;
# (b) enraizada nos indicadores da cartilha de desempenho que o RH já aprovou,
# não inventada; (c) preditiva do que de fato derruba a permanência num posto.
#
# Quatro e não oito: com 15 competências preenche-se no automático; com 4,
# pensa-se. O teto antes da "fadiga de avaliação" é 8; para cargos operacionais
# o alvo é 4.
# --------------------------------------------------------------------------

COMPETENCIAS = [
    {
        "chave": "confiabilidade",
        "nome": "Confiabilidade e presença",
        "raiz": "indicadores `assiduidade` e `pontualidade` da cartilha",
        "ancoras": {
            4: ("Cita situação concreta em que se antecipou a um imprevisto "
                "(saiu mais cedo por chuva, greve, problema no transporte) e "
                "descreve como avisou o responsável com antecedência."),
            3: ("Descreve rotina de transporte compatível com o horário do "
                "posto; quando faltou, avisou antes e justificou."),
            2: ("Fala de pontualidade em termos genéricos (\"sou pontual\"), sem "
                "exemplo; admite atrasos ocasionais sem descrever como comunicou."),
            1: ("Relata faltas ou atrasos sem aviso; atribui a terceiros sem ação "
                "própria; não consegue descrever como chegaria ao posto."),
        },
        "perguntas": {
            "comportamental": ("Conte uma vez em que você quase se atrasou para o "
                               "trabalho. O que você fez?"),
            "situacional": ("Você começa às 6h e às 5h descobre que a linha de "
                            "ônibus está parada. O que você faz?"),
        },
    },
    {
        "chave": "trato_publico",
        "nome": "Trato com público e postura sob pressão",
        "raiz": "indicador `relacionamento` da cartilha",
        "ancoras": {
            4: ("Descreve situação real de conflito com público e como conduziu "
                "sem escalar: o que falou, a quem acionou, como terminou. Separa "
                "o problema da pessoa."),
            3: ("Descreve postura adequada (ouvir, não responder no mesmo tom, "
                "chamar o supervisor), com exemplo ainda que simples."),
            2: ("Diz que \"leva na boa\" ou \"não discuto\", sem descrever o que "
                "faz concretamente."),
            1: ("Relata revide, ironia ou abandono do posto; culpa o público; ou "
                "não consegue imaginar a situação."),
        },
        "perguntas": {
            "comportamental": ("Conte uma vez em que alguém falou com você de forma "
                               "ríspida no trabalho. O que aconteceu?"),
            "situacional": ("Um visitante insiste em entrar sem crachá e começa a "
                            "levantar a voz. O que você faz?"),
        },
    },
    {
        "chave": "norma_procedimento",
        "nome": "Cumprimento de norma e procedimento",
        "raiz": "indicadores `normas_epi` e `uniforme` da cartilha",
        "ancoras": {
            4: ("Cita norma ou procedimento específico de trabalho anterior e por "
                "que existia; descreve ocasião em que cumpriu mesmo sendo "
                "inconveniente."),
            3: ("Reconhece a existência de regras (EPI, uniforme, registro de "
                "ponto, livro de ocorrência) e diz cumprir, com exemplo."),
            2: ("Responde de forma genérica (\"sigo as regras\") sem citar nenhuma; "
                "trata norma como formalidade."),
            1: ("Relata ter contornado procedimento por conveniência e não vê "
                "problema nisso; ou desconhece o que é EPI no contexto do cargo."),
        },
        "perguntas": {
            "comportamental": ("Me conta uma regra do seu trabalho anterior que você "
                               "achava chata mas cumpria. Por que ela existia?"),
            "situacional": ("É um dia muito quente e o EPI incomoda. Ninguém está "
                            "olhando. O que você faz?"),
        },
    },
    {
        "chave": "comunicacao_registro",
        "nome": "Comunicação e registro",
        "raiz": ("`qualidade` da cartilha + necessidade operacional real: vigia que "
                 "não sabe descrever ocorrência é problema concreto"),
        "ancoras": {
            4: ("Relata fato em ordem, com o essencial e sem invenção; quando não "
                "sabe algo, diz que não sabe. Descreve como registraria por escrito "
                "ou a quem comunicaria."),
            3: ("Consegue contar o que aconteceu de forma compreensível, mesmo sem "
                "organização perfeita."),
            2: ("Respostas muito curtas ou desorganizadas; precisa de várias "
                "perguntas para se fazer entender."),
            1: ("Não consegue relatar um fato simples de forma que se entenda; ou "
                "preenche lacunas com suposição apresentada como certeza."),
        },
        "perguntas": {
            "comportamental": ("Conte o que aconteceu no seu último dia de trabalho, "
                               "do começo ao fim."),
            "situacional": ("Você presencia uma discussão no hall e o supervisor pede "
                            "um relato. O que você diz a ele?"),
        },
    },
]

CHAVES_COMPETENCIA = [c["chave"] for c in COMPETENCIAS]

VARIANTES = [
    {"chave": "comportamental", "rotulo": "Comportamental (tem experiência no cargo)"},
    {"chave": "situacional", "rotulo": "Situacional (primeiro emprego / sem experiência)"},
]


# --------------------------------------------------------------------------
# Recomendação final
# --------------------------------------------------------------------------

RECOMENDACOES = [
    {"chave": "contratar", "rotulo": "Contratar", "exige_motivo": False},
    {"chave": "contratar_com_ressalva", "rotulo": "Contratar com ressalva",
     "exige_motivo": True},
    {"chave": "banco_para_outra_vaga", "rotulo": "Banco para outra vaga",
     "exige_motivo": True},
    {"chave": "nao_contratar", "rotulo": "Não contratar", "exige_motivo": False},
]

# As duas que EXIGEM motivo. "Com ressalva" sem dizer qual ressalva não é
# recomendação, é impressão — e é exatamente o que o módulo existe para acabar.
RECOMENDACOES_COM_MOTIVO = {r["chave"] for r in RECOMENDACOES if r["exige_motivo"]}
CHAVES_RECOMENDACAO = {r["chave"] for r in RECOMENDACOES}


# --------------------------------------------------------------------------
# TRIAGEM (§ 4.1) — checagem de viabilidade. Sem nota, sem competência, sem
# âncora. O que derruba a contratação em terceirização raramente é
# incapacidade: é escala que não cabe na vida, local inacessível, salário
# abaixo do esperado.
# --------------------------------------------------------------------------

PERGUNTAS_TRIAGEM = [
    {"chave": "aceita_escala",
     "pergunta": "A escala é 12×36 noturno. Isso cabe na sua rotina?"},
    {"chave": "aceita_salario",
     "pergunta": "A remuneração é R$ X. Está de acordo?"},
    {"chave": "consegue_chegar",
     "pergunta": "O posto fica em <local>. Você consegue chegar no horário?"},
    {"chave": "tem_interesse",
     "pergunta": "Você ainda tem interesse nessa vaga?"},
    {"chave": "recebe_seguro_desemprego",
     "pergunta": "Você está recebendo seguro-desemprego hoje?",
     # Registrado porque EXPLICA falta e desistência, e porque o dado do
     # cadastro público pode ter oito meses. NUNCA é critério de exclusão:
     # recusar alguém por receber seguro-desemprego não é decisão do sistema.
     "nunca_exclui": True},
]

CHAVES_TRIAGEM = [p["chave"] for p in PERGUNTAS_TRIAGEM]
RESPOSTAS_TRIAGEM = {"sim", "nao", "nao_sei"}

DESFECHOS_TRIAGEM = [
    {"chave": "segue", "rotulo": "Segue para entrevista"},
    {"chave": "nao_segue", "rotulo": "Não segue"},
    {"chave": "sem_contato", "rotulo": "Não consegui contato"},
]
CHAVES_DESFECHO_TRIAGEM = {d["chave"] for d in DESFECHOS_TRIAGEM}


# Retenção: 180 dias (decisão do Bruno). ARQUIVA, não apaga.
RETENCAO_PADRAO_DIAS = 180


def formulario() -> dict:
    """Tudo que o front precisa para desenhar as duas fichas — o front NÃO
    duplica competência, âncora nem pergunta (é o que `test_entrevista_instrumento`
    cobra estruturalmente)."""
    return {
        "escala": ESCALA,
        "competencias": COMPETENCIAS,
        "variantes": VARIANTES,
        "recomendacoes": RECOMENDACOES,
        "triagem": {
            "perguntas": PERGUNTAS_TRIAGEM,
            "respostas": sorted(RESPOSTAS_TRIAGEM),
            "desfechos": DESFECHOS_TRIAGEM,
        },
    }


def validar_triagem(triagem: dict | None, desfecho: str | None) -> list[str]:
    """Erros de preenchimento da triagem, em linguagem de tela. Vazio = pode
    salvar. A triagem é deliberadamente permissiva: "não sei" é resposta
    legítima, e a linha livre é opcional."""
    erros = []
    for chave, valor in (triagem or {}).items():
        if chave not in CHAVES_TRIAGEM:
            erros.append(f"Pergunta de triagem desconhecida: '{chave}'.")
        elif valor not in RESPOSTAS_TRIAGEM:
            erros.append(
                f"Resposta inválida em '{chave}': use sim, nao ou nao_sei.")
    if desfecho is not None and desfecho not in CHAVES_DESFECHO_TRIAGEM:
        erros.append(f"Desfecho de triagem inválido: '{desfecho}'.")
    return erros


def validar_entrevista(competencias: dict | None, justificativas: dict | None,
                       recomendacao: str | None,
                       recomendacao_motivo: str | None) -> list[str]:
    """Erros de preenchimento da avaliação, em linguagem de tela.

    Duas regras que NÃO devem ser afrouxadas:

    - **Nota sem justificativa não salva** (§ 2.3): âncora comportamental sem
      evidência escrita é o mesmo ruído que o módulo veio substituir. O erro
      NOMEIA a competência que falta — "faltou justificativa" genérico faria o
      RH procurar qual das quatro.
    - **`contratar_com_ressalva` e `banco_para_outra_vaga` exigem motivo**.
    """
    erros = []
    nomes = {c["chave"]: c["nome"] for c in COMPETENCIAS}

    for chave, valor in (competencias or {}).items():
        if chave not in nomes:
            erros.append(f"Competência desconhecida: '{chave}'.")
        elif valor not in VALORES_VALIDOS:
            erros.append(f"Nota inválida em '{nomes[chave]}': use 1 a 4.")

    # A justificativa é cobrada por NOTA DADA — competência ainda não avaliada
    # não cobra nada (o RH pode salvar um rascunho parcial).
    for chave, valor in (competencias or {}).items():
        if chave not in nomes or valor not in VALORES_VALIDOS:
            continue
        texto = ((justificativas or {}).get(chave) or "").strip()
        if not texto:
            erros.append(f"Justifique a nota de '{nomes[chave]}'.")

    if recomendacao is not None:
        if recomendacao not in CHAVES_RECOMENDACAO:
            erros.append(f"Recomendação inválida: '{recomendacao}'.")
        elif (recomendacao in RECOMENDACOES_COM_MOTIVO
                and not (recomendacao_motivo or "").strip()):
            rotulo = next(r["rotulo"] for r in RECOMENDACOES
                          if r["chave"] == recomendacao)
            erros.append(f"'{rotulo}' exige o motivo.")
    return erros


def completa_entrevista(competencias: dict | None,
                        recomendacao: str | None) -> list[str]:
    """O que falta para a entrevista poder ser CONCLUÍDA (status realizada).
    Salvar rascunho parcial continua permitido — o que não se permite é fechar
    a avaliação pela metade."""
    faltando = []
    respondidas = set((competencias or {}).keys())
    if not respondidas >= set(CHAVES_COMPETENCIA):
        nomes = {c["chave"]: c["nome"] for c in COMPETENCIAS}
        faltam = [nomes[c] for c in CHAVES_COMPETENCIA if c not in respondidas]
        faltando.append("competências sem nota: " + ", ".join(faltam))
    if not (recomendacao or "").strip():
        faltando.append("recomendação final")
    return faltando


def media(competencias: dict | None) -> float | None:
    """Média 1–4 das competências pontuadas. Sem competência, sem média (None,
    nunca 0 — zero seria uma nota, e a ausência de nota não é nota baixa)."""
    if not competencias:
        return None
    notas = [v for v in competencias.values() if v in VALORES_VALIDOS]
    return round(sum(notas) / len(notas), 2) if notas else None


def defasagem_dias(realizada_em, preenchida_em) -> int | None:
    """Quantos dias separam a entrevista do preenchimento (§ 2.5).

    Existe porque quem preenche no dia seguinte RECONSTRÓI em vez de lembrar. A
    resposta não é proibir (o RH deixaria de registrar), é CARIMBAR na tela.
    """
    if realizada_em is None or preenchida_em is None:
        return None
    dias = (preenchida_em - realizada_em).days
    return dias if dias > 0 else 0
