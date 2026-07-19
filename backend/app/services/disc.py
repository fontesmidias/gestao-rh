"""Inventário Comportamental DISC + Teste Situacional.

DISC: 24 questões de escolha forçada (4 adjetivos; o candidato marca UM que
"MAIS" e UM que "MENOS" tem a ver com ele), no formato do inventário fornecido
pelo RH. Cada questão traz exatamente um adjetivo de cada dimensão:
  D (Dominância) · I (Influência) · S (eStabilidade) · C (Conformidade)
As questões 5 e 19 (sem print no material do RH) foram construídas seguindo a
mesma lógica, sem repetir adjetivos.

Pontuação (método clássico dos inventários de adjetivos): conta-se quantos
"MAIS" e quantos "MENOS" o candidato marcou em cada dimensão; o escore da
dimensão é MAIS - MENOS. O(s) maior(es) escore(s) definem o perfil predominante.

IMPORTANTE (amparo legal/ético):
- Este é um INVENTÁRIO COMPORTAMENTAL de apoio à gestão de pessoas. NÃO é
  teste psicológico (avaliação psicológica é privativa de psicólogo —
  Lei 4.119/1962 e Resolução CFP nº 31/2022) e NÃO deve ser usado como critério
  único de decisão.
- O RESULTADO É RESTRITO AO RH; o candidato não o recebe.
- O mapa de dimensões (gabarito) NUNCA é enviado ao frontend.
- Dados tratados conforme a LGPD, com consentimento colhido na entrada.
"""

# ---------------------------------------------------------------------------
# DISC — 24 questões. Cada tupla: (adjetivo, dimensão). A ordem dos adjetivos
# é a exibida ao candidato (a mesma dos prints do RH).
# ---------------------------------------------------------------------------

QUESTOES_DISC: list[list[tuple[str, str]]] = [
    # 1
    [("Bondoso", "S"), ("Persuasivo", "I"), ("Modesto", "C"), ("Original", "D")],
    # 2
    [("Envolvente", "I"), ("Cooperativo", "C"), ("Teimoso", "D"), ("Afetuoso", "S")],
    # 3
    [("Conformado", "C"), ("Pioneiro", "D"), ("Leal", "S"), ("Animado", "I")],
    # 4
    [("Aberto", "C"), ("Prestativo", "S"), ("Determinado", "D"), ("Alegre", "I")],
    # 5 — construída (sem print no material do RH)
    [("Corajoso", "D"), ("Expressivo", "I"), ("Calmo", "S"), ("Meticuloso", "C")],
    # 6
    [("Competitivo", "D"), ("Atencioso", "C"), ("Feliz", "I"), ("Harmonioso", "S")],
    # 7
    [("Preciso", "C"), ("Obediente", "S"), ("Dominante", "D"), ("Divertido", "I")],
    # 8
    [("Destemido", "D"), ("Inspirador", "I"), ("Submisso", "S"), ("Tímido", "C")],
    # 9
    [("Sociável", "I"), ("Tolerante", "S"), ("Autoconfiante", "D"), ("Contido", "C")],
    # 10
    [("Arrojado", "D"), ("Receptivo", "S"), ("Amigável", "I"), ("Moderado", "C")],
    # 11
    [("Comunicativo", "I"), ("Reservado", "S"), ("Convencional", "C"), ("Decidido", "D")],
    # 12
    [("Polido", "I"), ("Audacioso", "D"), ("Diplomático", "C"), ("Sereno", "S")],
    # 13
    [("Firme", "D"), ("Carismático", "I"), ("Acolhedor", "S"), ("Receoso", "C")],
    # 14
    [("Cuidadoso", "C"), ("Resoluto", "D"), ("Influente", "I"), ("Bom Temperamento", "S")],
    # 15
    [("Solidário", "S"), ("Entusiasmado", "I"), ("Conciliador", "C"), ("Dinâmico", "D")],
    # 16
    [("Otimista", "I"), ("Compreensivo", "C"), ("Paciente", "S"), ("Exigente", "D")],
    # 17
    [("Disciplinado", "C"), ("Generoso", "S"), ("Convincente", "I"), ("Ambicioso", "D")],
    # 18
    [("Admirável", "I"), ("Amável", "S"), ("Resignado", "C"), ("Enérgico", "D")],
    # 19 — construída (sem print no material do RH)
    [("Ousado", "D"), ("Espontâneo", "I"), ("Constante", "S"), ("Perfeccionista", "C")],
    # 20
    [("Agressivo", "D"), ("Adaptável", "C"), ("Tranquilo", "S"), ("Descontraído", "I")],
    # 21
    [("Crédulo", "I"), ("Satisfeito", "C"), ("Positivo", "D"), ("Pacífico", "S")],
    # 22
    [("Agradável", "I"), ("Culto", "C"), ("Vigoroso", "D"), ("Complacente", "S")],
    # 23
    [("Bom Companheiro", "I"), ("Exato", "C"), ("Franco", "D"), ("Cauteloso", "S")],
    # 24
    [("Impaciente", "D"), ("Bom vizinho", "S"), ("Popular", "I"), ("Metódico", "C")],
]

TEMPO_DISC_SEGUNDOS = 12 * 60  # 12 minutos, como no inventário de referência


# Significado de cada adjetivo, para o tooltip do candidato (feedback
# 2026-07-19: quem não sabe o que "Afetuoso" quer dizer não precisa sair da
# plataforma para pesquisar). REGRA: são SINÔNIMOS CURTOS E NEUTROS — dão o
# sentido da palavra, NUNCA descrevem um perfil/traço de personalidade. Uma
# descrição que dissesse "pessoa calorosa, voltada a relacionamentos" entregaria
# o eixo DISC do adjetivo e permitiria gamear o inventário. Por isso são
# escritas à mão, uma a uma, e revisadas para não vazar o gabarito. Vão ao
# lado PÚBLICO; o mapa de dimensões continua só no servidor.
SIGNIFICADOS_DISC: dict[str, str] = {
    "Bondoso": "que tem bondade; de bom coração",
    "Persuasivo": "que convence com facilidade",
    "Modesto": "sem exibição; simples",
    "Original": "criativo; fora do comum",
    "Envolvente": "que atrai e prende a atenção",
    "Cooperativo": "que colabora; que ajuda",
    "Teimoso": "que insiste na própria opinião",
    "Afetuoso": "que demonstra carinho",
    "Conformado": "que aceita as coisas como são",
    "Pioneiro": "que faz algo pela primeira vez",
    "Leal": "fiel; de confiança",
    "Animado": "cheio de energia e disposição",
    "Aberto": "receptivo a ideias e pessoas",
    "Prestativo": "que gosta de ajudar",
    "Determinado": "firme na decisão",
    "Alegre": "de bom humor; contente",
    "Corajoso": "que enfrenta o medo",
    "Expressivo": "que se comunica com emoção",
    "Calmo": "tranquilo; sem agitação",
    "Meticuloso": "que cuida de cada detalhe",
    "Competitivo": "que gosta de competir",
    "Atencioso": "que presta atenção; cuidadoso",
    "Feliz": "contente; satisfeito",
    "Harmonioso": "que vive em harmonia; equilibrado",
    "Preciso": "exato; sem erro",
    "Obediente": "que segue o que é pedido",
    "Dominante": "que costuma comandar",
    "Divertido": "que gera diversão; engraçado",
    "Destemido": "sem medo",
    "Inspirador": "que motiva os outros",
    "Submisso": "que se sujeita facilmente",
    "Tímido": "acanhado; retraído",
    "Sociável": "que gosta de conviver",
    "Tolerante": "que aceita as diferenças",
    "Autoconfiante": "que confia em si mesmo",
    "Contido": "reservado; comedido",
    "Arrojado": "ousado; que arrisca",
    "Receptivo": "aberto a receber ideias",
    "Amigável": "que faz amizade com facilidade",
    "Moderado": "equilibrado; sem exageros",
    "Comunicativo": "que fala e se expressa com facilidade",
    "Reservado": "discreto; que fala pouco de si",
    "Convencional": "que segue o comum; tradicional",
    "Decidido": "que decide com firmeza",
    "Polido": "educado; gentil",
    "Audacioso": "atrevido; que ousa",
    "Diplomático": "que lida bem com conflitos",
    "Sereno": "calmo e equilibrado",
    "Firme": "seguro; que não vacila",
    "Carismático": "que atrai simpatia",
    "Acolhedor": "que recebe bem as pessoas",
    "Receoso": "que sente receio; cauteloso",
    "Cuidadoso": "que age com cuidado",
    "Resoluto": "decidido; sem hesitar",
    "Influente": "que tem influência sobre os outros",
    "Bom Temperamento": "de trato fácil e agradável",
    "Solidário": "que apoia os outros",
    "Entusiasmado": "muito animado; empolgado",
    "Conciliador": "que busca o acordo",
    "Dinâmico": "ativo; cheio de energia",
    "Otimista": "que vê o lado positivo",
    "Compreensivo": "que entende os outros",
    "Paciente": "que espera com calma",
    "Exigente": "que cobra muito; rigoroso",
    "Disciplinado": "que segue regras e rotina",
    "Generoso": "que dá com boa vontade",
    "Convincente": "que convence",
    "Ambicioso": "que busca conquistar mais",
    "Admirável": "digno de admiração",
    "Amável": "gentil; afável",
    "Resignado": "que aceita sem reclamar",
    "Enérgico": "cheio de energia; vigoroso",
    "Ousado": "que ousa; corajoso",
    "Espontâneo": "natural; sem forçar",
    "Constante": "que se mantém igual ao longo do tempo",
    "Perfeccionista": "que busca a perfeição",
    "Agressivo": "que age com força ou dureza",
    "Adaptável": "que se ajusta às situações",
    "Tranquilo": "calmo; sossegado",
    "Descontraído": "à vontade; relaxado",
    "Crédulo": "que acredita com facilidade",
    "Satisfeito": "contente com o que tem",
    "Positivo": "que pensa de forma otimista",
    "Pacífico": "que evita conflitos",
    "Agradável": "que agrada; simpático",
    "Culto": "que tem cultura e conhecimento",
    "Vigoroso": "forte; cheio de vigor",
    "Complacente": "que cede com facilidade",
    "Bom Companheiro": "que é boa companhia",
    "Exato": "preciso; correto",
    "Franco": "sincero; direto",
    "Cauteloso": "que age com cautela",
    "Impaciente": "que não gosta de esperar",
    "Bom vizinho": "cordial no convívio",
    "Popular": "querido por muitos",
    "Metódico": "que age com método e ordem",
}


def questoes_disc_publicas() -> list[dict]:
    """Questões SEM o mapa de dimensões (o gabarito nunca vai ao front). Inclui
    o significado neutro de cada adjetivo para o tooltip do candidato."""
    return [
        {"numero": i + 1,
         "opcoes": [{"palavra": adj, "significado": SIGNIFICADOS_DISC.get(adj, "")}
                    for adj, _dim in grupo]}
        for i, grupo in enumerate(QUESTOES_DISC)
    ]


def pontuar_disc(respostas: list[dict]) -> dict:
    """respostas: [{"questao": 1, "mais": "Bondoso", "menos": "Original"}, ...]
    Devolve escores por dimensão + perfil predominante + percentuais p/ gráfico."""
    mais = {"D": 0, "I": 0, "S": 0, "C": 0}
    menos = {"D": 0, "I": 0, "S": 0, "C": 0}
    respondidas = 0
    for r in respostas:
        n = r.get("questao")
        if not isinstance(n, int) or not (1 <= n <= len(QUESTOES_DISC)):
            continue
        grupo = {adj: dim for adj, dim in QUESTOES_DISC[n - 1]}
        dim_mais = grupo.get(r.get("mais"))
        dim_menos = grupo.get(r.get("menos"))
        if not dim_mais or not dim_menos or r.get("mais") == r.get("menos"):
            continue
        mais[dim_mais] += 1
        menos[dim_menos] += 1
        respondidas += 1

    escores = {d: mais[d] - menos[d] for d in "DISC"}
    # normalização para o gráfico (0-100): desloca pelo mínimo teórico
    n = max(respondidas, 1)
    percentuais = {d: round((escores[d] + n) / (2 * n) * 100) for d in "DISC"}
    ordenado = sorted("DISC", key=lambda d: escores[d], reverse=True)
    principal = ordenado[0]
    # dimensão secundária entra no perfil quando fica "perto" da principal
    secundaria = ordenado[1] if escores[ordenado[1]] >= escores[principal] - 2 \
        and escores[ordenado[1]] > 0 else None
    return {
        "respondidas": respondidas,
        "mais": mais, "menos": menos, "escores": escores,
        "percentuais": percentuais,
        "principal": principal, "secundaria": secundaria,
        "perfil": principal + (secundaria or ""),
    }


# Textos dos perfis: linguagem de gestão (não clínica), com pontos fortes e de
# atenção — para o RH interpretar com equilíbrio.
PERFIS_DISC = {
    "D": {
        "nome": "Dominância",
        "resumo": "Orientado(a) a resultados, direto(a) e decidido(a). Gosta de "
                  "desafios, assume riscos e busca o controle da situação.",
        "fortes": "Iniciativa, foco em metas, rapidez na decisão, senso de urgência.",
        "atencao": "Pode ser impaciente com processos e pessoas de ritmo diferente; "
                   "atenção à escuta e à delegação.",
        "ambiente": "Rende mais com autonomia, metas claras e espaço para decidir.",
    },
    "I": {
        "nome": "Influência",
        "resumo": "Comunicativo(a), entusiasmado(a) e persuasivo(a). Constrói "
                  "relacionamentos com facilidade e contagia o ambiente.",
        "fortes": "Comunicação, otimismo, networking, capacidade de engajar pessoas.",
        "atencao": "Pode dispersar o foco e evitar tarefas detalhistas; atenção a "
                   "prazos e follow-up.",
        "ambiente": "Rende mais com interação, reconhecimento e variedade.",
    },
    "S": {
        "nome": "Estabilidade",
        "resumo": "Paciente, leal e colaborativo(a). Valoriza a harmonia, a "
                  "segurança e a constância nas relações e nas rotinas.",
        "fortes": "Trabalho em equipe, escuta, consistência, apoio aos colegas.",
        "atencao": "Pode resistir a mudanças bruscas e evitar conflitos "
                   "necessários; atenção ao posicionamento.",
        "ambiente": "Rende mais com previsibilidade, cooperação e mudanças graduais.",
    },
    "C": {
        "nome": "Conformidade",
        "resumo": "Analítico(a), preciso(a) e disciplinado(a). Preza pela "
                  "qualidade, pelas regras e pelo trabalho bem feito.",
        "fortes": "Atenção a detalhes, organização, senso crítico, cumprimento de normas.",
        "atencao": "Pode ser perfeccionista e ter dificuldade com ambiguidade; "
                   "atenção à flexibilidade e à comunicação de riscos.",
        "ambiente": "Rende mais com critérios claros, tempo para análise e qualidade valorizada.",
    },
}


# ---------------------------------------------------------------------------
# Teste Situacional (julgamento situacional no trabalho). Sério e objetivo:
# cada situação tem 4 condutas; o candidato escolhe a que MAIS se aproxima do
# que faria. Pontuação 0-3 por questão (3 = melhor prática de conduta
# profissional). O resultado (percentual + faixa) é restrito ao RH.
# ---------------------------------------------------------------------------

QUESTOES_SITUACIONAL: list[dict] = [
    {
        "numero": 1,
        "situacao": "Você percebe que cometeu um erro em uma tarefa importante e "
                    "ninguém notou ainda. O prazo de entrega é hoje.",
        "opcoes": [
            ("Comunico imediatamente meu superior, explico o erro e proponho como corrigir.", 3),
            ("Corrijo em silêncio, sem contar a ninguém, para não gerar alarde.", 1),
            ("Espero para ver se alguém percebe antes de me manifestar.", 0),
            ("Conto a um colega de confiança e peço a opinião dele antes de agir.", 2),
        ],
    },
    {
        "numero": 2,
        "situacao": "Um colega de equipe está visivelmente sobrecarregado e "
                    "atrasando entregas que afetam o seu trabalho.",
        "opcoes": [
            ("Ofereço ajuda no que estiver ao meu alcance e, se persistir, converso com o gestor em conjunto.", 3),
            ("Reclamo diretamente com o gestor sobre o atraso do colega.", 1),
            ("Ignoro: cada um é responsável pela própria parte.", 0),
            ("Converso com o colega para entender a situação antes de qualquer coisa.", 2),
        ],
    },
    {
        "numero": 3,
        "situacao": "Você recebe uma instrução do seu superior que contraria um "
                    "procedimento de segurança da empresa.",
        "opcoes": [
            ("Exponho respeitosamente a divergência ao superior e, se mantida, registro e reporto ao canal competente.", 3),
            ("Cumpro a instrução: ordem é ordem.", 0),
            ("Não cumpro e não comento nada com ninguém.", 1),
            ("Peço a orientação por escrito antes de executar.", 2),
        ],
    },
    {
        "numero": 4,
        "situacao": "Um cliente/usuário trata você com grosseria na frente de "
                    "outras pessoas.",
        "opcoes": [
            ("Mantenho a calma e a cordialidade, resolvo a demanda e, se necessário, aciono meu superior.", 3),
            ("Respondo no mesmo tom para impor respeito.", 0),
            ("Peço que outro colega o atenda no meu lugar.", 1),
            ("Escuto em silêncio, resolvo o que der e desabafo depois com colegas.", 2),
        ],
    },
    {
        "numero": 5,
        "situacao": "Você encontra um objeto de valor esquecido em uma área comum "
                    "do posto de trabalho.",
        "opcoes": [
            ("Entrego imediatamente ao responsável da área/segurança e registro a ocorrência.", 3),
            ("Guardo comigo até alguém procurar.", 1),
            ("Deixo onde está: não é problema meu.", 0),
            ("Pergunto aos colegas próximos de quem é antes de acionar o responsável.", 2),
        ],
    },
    {
        "numero": 6,
        "situacao": "Faltam 10 minutos para o fim do seu expediente e surge uma "
                    "demanda urgente que levaria cerca de 30 minutos.",
        "opcoes": [
            ("Avalio a urgência com o superior: se for crítico, permaneço e depois acerto a compensação.", 3),
            ("Vou embora no horário: demanda nova é do próximo turno.", 1),
            ("Fico sem avisar ninguém e resolvo sozinho(a).", 2),
            ("Digo que não posso e sugiro que chamem outra pessoa.", 0),
        ],
    },
    {
        "numero": 7,
        "situacao": "Você fica sabendo de um boato negativo (não confirmado) sobre "
                    "um colega de trabalho.",
        "opcoes": [
            ("Não repasso o boato e, se ele prejudicar o ambiente, alerto o RH/gestão sem expor ninguém.", 3),
            ("Comento com outros colegas para saber se é verdade.", 0),
            ("Conto ao próprio colega imediatamente, com detalhes de quem falou.", 1),
            ("Ignoro completamente, mesmo que o ambiente piore.", 2),
        ],
    },
    {
        "numero": 8,
        "situacao": "A empresa muda um procedimento que você executava há anos de "
                    "um jeito que considera melhor.",
        "opcoes": [
            ("Sigo o novo procedimento e levo minha sugestão de melhoria pelo canal adequado.", 3),
            ("Continuo fazendo do meu jeito, que é comprovadamente melhor.", 0),
            ("Sigo o novo, mas comento com os colegas que não vai dar certo.", 1),
            ("Peço ao gestor uma conversa para entender o motivo da mudança.", 2),
        ],
    },
    {
        "numero": 9,
        "situacao": "Você presencia um colega sofrendo um tratamento desrespeitoso "
                    "recorrente de um superior.",
        "opcoes": [
            ("Acolho o colega e o oriento a registrar; se persistir, reporto ao canal de denúncias/RH.", 3),
            ("Não me envolvo: é problema entre eles.", 0),
            ("Enfrento o superior na hora, na frente de todos.", 1),
            ("Converso reservadamente com o colega para saber se ele quer ajuda.", 2),
        ],
    },
    {
        "numero": 10,
        "situacao": "Você termina suas tarefas do dia mais cedo que o previsto.",
        "opcoes": [
            ("Aviso o superior e me coloco à disposição para apoiar a equipe ou antecipar demandas.", 3),
            ("Uso o tempo para resolver assuntos pessoais discretamente.", 0),
            ("Reviso meu próprio trabalho até o fim do expediente.", 2),
            ("Espero em silêncio novas ordens.", 1),
        ],
    },
]

TEMPO_SITUACIONAL_SEGUNDOS = 15 * 60


def questoes_situacional_publicas() -> list[dict]:
    """Sem a pontuação (o gabarito nunca vai ao front). A ordem das opções é
    embaralhada de forma DETERMINÍSTICA por questão (evita 'a primeira é sempre
    a certa' sem quebrar a correção)."""
    saida = []
    for q in QUESTOES_SITUACIONAL:
        opcoes = [texto for texto, _p in q["opcoes"]]
        # rotação determinística pelo número da questão (estável entre sessões)
        rot = q["numero"] % len(opcoes)
        opcoes = opcoes[rot:] + opcoes[:rot]
        saida.append({"numero": q["numero"], "situacao": q["situacao"], "opcoes": opcoes})
    return saida


def pontuar_situacional(respostas: list[dict]) -> dict:
    """respostas: [{"questao": 1, "escolha": "texto da opção"}, ...]"""
    gabarito = {q["numero"]: dict(q["opcoes"]) for q in QUESTOES_SITUACIONAL}
    total = 0
    maximo = 3 * len(QUESTOES_SITUACIONAL)
    respondidas = 0
    for r in respostas:
        pontos = gabarito.get(r.get("questao"), {}).get(r.get("escolha"))
        if pontos is None:
            continue
        total += pontos
        respondidas += 1
    pct = round(total / maximo * 100) if maximo else 0
    faixa = ("Excelente" if pct >= 85 else "Bom" if pct >= 70
             else "Adequado" if pct >= 50 else "Atenção")
    return {"respondidas": respondidas, "pontos": total, "maximo": maximo,
            "percentual": pct, "faixa": faixa}
