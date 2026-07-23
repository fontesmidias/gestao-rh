"""Regras da avaliação de desempenho (Onda C).

O instrumento é a cartilha `docs/Cartilha do Avaliador e Formulário, de
17-06-2026.pdf`, que já rodava no Microsoft Forms. As escalas, os 7 indicadores,
as 8 competências e as 5 recomendações estão aqui **palavra por palavra** — não
foram inventados, e mudá-los muda o instrumento oficial do RH.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.desempenho import (Avaliacao, RelacaoAvaliador, StatusAvaliacao)

# --- Escalas (cartilha, pág. 3) -------------------------------------------
# Indicadores objetivos: assiduidade, qualidade, normas/EPI…
ESCALA_INDICADOR = [
    {"valor": "atende", "rotulo": "Atende",
     "descricao": "Cumpre o esperado para a função de forma consistente no período."},
    {"valor": "parcial", "rotulo": "Atende parcial",
     "descricao": "Cumpre de forma irregular; oscila e precisa de acompanhamento."},
    {"valor": "nao_atende", "rotulo": "Não atende",
     "descricao": "Está abaixo do exigido; requer ação imediata."},
    {"valor": "na", "rotulo": "Não se aplica",
     "descricao": "O item não faz parte da rotina do cargo neste período."},
]

# Competências: proatividade, comunicação, trabalho em equipe…
ESCALA_COMPETENCIA = [
    {"valor": "nao_atende", "rotulo": "Não atende", "peso": 1,
     "descricao": "Comportamento ausente ou abaixo do exigido."},
    {"valor": "parcial", "rotulo": "Parcial", "peso": 2,
     "descricao": "Demonstra de forma inconsistente; precisa desenvolver."},
    {"valor": "adequado", "rotulo": "Adequado", "peso": 3,
     "descricao": "Atende ao esperado para a função de forma consistente."},
    {"valor": "elevado", "rotulo": "Elevado", "peso": 4,
     "descricao": "Supera o esperado e serve de referência para os colegas."},
    {"valor": "na", "rotulo": "N/A", "peso": None,
     "descricao": "Não se aplica ao cargo no período."},
]

# --- Seção 2: indicadores objetivos do período ----------------------------
INDICADORES = [
    {"chave": "assiduidade", "rotulo": "Assiduidade (faltas / ausências)"},
    {"chave": "pontualidade", "rotulo": "Pontualidade e cumprimento de jornada"},
    {"chave": "qualidade", "rotulo": "Qualidade e capricho na execução das tarefas"},
    {"chave": "produtividade", "rotulo": "Produtividade / ritmo de trabalho"},
    {"chave": "normas_epi", "rotulo": "Cumprimento de normas, procedimentos e uso de EPI"},
    {"chave": "uniforme", "rotulo": "Apresentação pessoal e uso correto do uniforme"},
    {"chave": "relacionamento", "rotulo": "Relacionamento com equipe, liderança e cliente"},
]

# --- Seção 3: matriz de competências --------------------------------------
# As de GESTÃO só se aplicam a cargo de liderança; nos demais, marcar N/A.
COMPETENCIAS = [
    {"chave": "lideranca_integradora", "rotulo": "Liderança integradora", "nivel": "Gestão"},
    {"chave": "excelencia_gestao", "rotulo": "Excelência em gestão", "nivel": "Gestão"},
    {"chave": "proatividade", "rotulo": "Proatividade", "nivel": "Transversais"},
    {"chave": "comprometimento", "rotulo": "Comprometimento", "nivel": "Transversais"},
    {"chave": "comunicacao", "rotulo": "Comunicação", "nivel": "Transversais"},
    {"chave": "planejamento", "rotulo": "Planejamento e organização", "nivel": "Transversais"},
    {"chave": "trabalho_equipe", "rotulo": "Trabalho em equipe", "nivel": "Transversais"},
    {"chave": "empatia", "rotulo": "Empatia", "nivel": "Transversais"},
]

# --- Seção 7: recomendação do gestor --------------------------------------
RECOMENDACOES = [
    {"valor": "efetivar", "rotulo": "Efetivar (período de experiência atendido)"},
    {"valor": "prorrogar", "rotulo": "Prorrogar período de experiência",
     "pede_data": True},
    {"valor": "nao_efetivar", "rotulo": "Não efetivar / desligar"},
    {"valor": "manter", "rotulo": "Manter com acompanhamento (avaliação periódica)"},
    {"valor": "plano_acao", "rotulo": "Plano de ação com reavaliação", "pede_data": True},
]

POSTURAS = [
    {"valor": "receptivo", "rotulo": "Receptivo"},
    {"valor": "neutro", "rotulo": "Neutro"},
    {"valor": "resistente", "rotulo": "Resistente"},
]

_PESO = {e["valor"]: e["peso"] for e in ESCALA_COMPETENCIA}
_VALIDOS_INDICADOR = {e["valor"] for e in ESCALA_INDICADOR}
_VALIDOS_COMPETENCIA = {e["valor"] for e in ESCALA_COMPETENCIA}

# Quantos respondentes horizontais são necessários para mostrar o agregado.
# Supressão de célula, como estatística oficial: agregado de UM é o individual
# com outro nome, e o anonimato do par morreria na primeira semana.
MINIMO_HORIZONTAL = 2


def formulario() -> dict:
    """Tudo que o front precisa para desenhar o formulário da cartilha."""
    return {
        "escala_indicador": ESCALA_INDICADOR,
        "escala_competencia": ESCALA_COMPETENCIA,
        "indicadores": INDICADORES,
        "competencias": COMPETENCIAS,
        "recomendacoes": RECOMENDACOES,
        "posturas": POSTURAS,
    }


def validar_respostas(indicadores: dict | None, competencias: dict | None) -> list[str]:
    """Erros de preenchimento, em linguagem de tela. Vazio = pode salvar."""
    erros = []
    for chave, valor in (indicadores or {}).items():
        if valor not in _VALIDOS_INDICADOR:
            erros.append(f"Indicador '{chave}' com valor inválido.")
    for chave, valor in (competencias or {}).items():
        if valor not in _VALIDOS_COMPETENCIA:
            erros.append(f"Competência '{chave}' com valor inválido.")
    return erros


def completa(avaliacao: Avaliacao) -> list[str]:
    """O que falta para a avaliação poder ser enviada. A cartilha manda não
    deixar recomendação sem justificativa (pág. 5, "Evite")."""
    faltando = []
    respondidos = set((avaliacao.indicadores or {}).keys())
    if not respondidos >= {i["chave"] for i in INDICADORES}:
        faltando.append("indicadores objetivos")
    respondidas = set((avaliacao.competencias or {}).keys())
    if not respondidas >= {c["chave"] for c in COMPETENCIAS}:
        faltando.append("matriz de competências")
    if not (avaliacao.recomendacao or "").strip():
        faltando.append("recomendação")
    elif not (avaliacao.justificativa or "").strip():
        # regra da cartilha: recomendação SEM justificativa não vale
        faltando.append("justificativa da recomendação")
    return faltando


def media_competencias(competencias: dict | None) -> float | None:
    """Média 1-4 das competências pontuáveis. N/A é ignorado (não é zero — o
    item não se aplica ao cargo, e contá-lo como zero puniria o avaliado)."""
    if not competencias:
        return None
    pesos = [_PESO[v] for v in competencias.values()
             if v in _PESO and _PESO[v] is not None]
    return round(sum(pesos) / len(pesos), 2) if pesos else None


def radar(db: Session, candidato_id, ciclo_id=None) -> dict:
    """Dados do gráfico de teia — 8 eixos, exatamente as competências da seção 3.

    O horizontal entra AGREGADO e só com `MINIMO_HORIZONTAL` respondentes; o
    vertical entra identificado. Não é enfeite de dashboard: é o material da
    conversa de feedback, que o gestor abre na frente da pessoa.
    """
    consulta = select(Avaliacao).where(
        Avaliacao.candidato_id == candidato_id,
        Avaliacao.status.in_([StatusAvaliacao.preenchida,
                              StatusAvaliacao.feedback_dado,
                              StatusAvaliacao.manifestada,
                              StatusAvaliacao.homologada]))
    if ciclo_id:
        consulta = consulta.where(Avaliacao.ciclo_id == ciclo_id)
    avaliacoes = db.scalars(consulta).all()

    por_relacao = {"vertical": [], "horizontal": [], "autoavaliacao": []}
    for a in avaliacoes:
        por_relacao[a.relacao.value].append(a.competencias or {})

    eixos = []
    for comp in COMPETENCIAS:
        linha = {"chave": comp["chave"], "rotulo": comp["rotulo"],
                 "nivel": comp["nivel"]}
        for relacao, lista in por_relacao.items():
            notas = [_PESO[c[comp["chave"]]] for c in lista
                     if c.get(comp["chave"]) in _PESO
                     and _PESO[c[comp["chave"]]] is not None]
            if relacao == "horizontal" and len(lista) < MINIMO_HORIZONTAL:
                # supressão: com menos de 2 pares, o "agregado" identificaria
                linha[relacao] = None
            else:
                linha[relacao] = (round(sum(notas) / len(notas), 2)
                                  if notas else None)
        eixos.append(linha)

    return {
        "eixos": eixos,
        "respondentes": {k: len(v) for k, v in por_relacao.items()},
        "horizontal_suprimido": len(por_relacao["horizontal"]) < MINIMO_HORIZONTAL
                                and len(por_relacao["horizontal"]) > 0,
        "minimo_horizontal": MINIMO_HORIZONTAL,
    }


def desvio_do_avaliador(db: Session, avaliador: str, ciclo_id=None) -> dict | None:
    """Quanto ESTE avaliador difere da média geral — informação para o
    homologador, **não** correção automática da nota.

    Por quê não normalizar: com 3 avaliados por líder o z-score é ruído puro; e
    quando a pessoa descobre que a nota que viu não é a que o líder deu, a
    confiança no sistema acaba. Distribuição forçada foi VETADA (a GE abandonou,
    a Microsoft matou em 2013).

    "Este avaliador dá em média 4,6; a média geral é 3,8" — o homologador decide
    o que fazer com isso. Ninguém acorda querendo ser injusto: quem dá nota alta
    para todo mundo geralmente não sabe que faz isso.
    """
    consulta = select(Avaliacao).where(Avaliacao.status.in_(
        [StatusAvaliacao.preenchida, StatusAvaliacao.feedback_dado,
         StatusAvaliacao.manifestada, StatusAvaliacao.homologada]))
    if ciclo_id:
        consulta = consulta.where(Avaliacao.ciclo_id == ciclo_id)
    todas = db.scalars(consulta).all()

    minhas = [media_competencias(a.competencias) for a in todas
              if a.avaliador == avaliador]
    minhas = [m for m in minhas if m is not None]
    geral = [media_competencias(a.competencias) for a in todas]
    geral = [m for m in geral if m is not None]
    if not minhas or len(geral) < 2:
        return None

    media_avaliador = round(sum(minhas) / len(minhas), 2)
    media_geral = round(sum(geral) / len(geral), 2)
    diferenca = round(media_avaliador - media_geral, 2)
    return {
        "avaliador": avaliador,
        "media_avaliador": media_avaliador,
        "media_geral": media_geral,
        "diferenca": diferenca,
        "avaliacoes": len(minhas),
        # tendência só quando a diferença é grande o bastante para significar
        # algo (meio ponto numa escala de 1 a 4)
        "tendencia": ("mais generoso" if diferenca >= 0.5
                      else "mais rigoroso" if diferenca <= -0.5 else "alinhado"),
    }


def fatos_do_periodo(db: Session, candidato_id, inicio: date | None,
                     fim: date | None) -> list:
    """Fatos observados dentro do período avaliado — é o que o formulário mostra
    ao lado, para o líder REVISAR o que já registrou em vez de escrever do zero.
    """
    from app.models.desempenho import FatoObservado
    consulta = select(FatoObservado).where(
        FatoObservado.candidato_id == candidato_id)
    if inicio:
        consulta = consulta.where(FatoObservado.ocorrido_em >= inicio)
    if fim:
        consulta = consulta.where(FatoObservado.ocorrido_em <= fim)
    return db.scalars(consulta.order_by(FatoObservado.ocorrido_em.desc())).all()
