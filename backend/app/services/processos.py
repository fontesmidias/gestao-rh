"""Carteira de Processos: a cadeia, a carga e quem responde HOJE (v2.91).

A pergunta que este módulo existe para responder é a do Bruno: *"caso haja
algum funcionário substituído, indo embora do RH ou qualquer outra coisa, tenha
uma organização de processos"*. Ou seja: **quem responde por isto agora, se o
titular não está?**

Duas regras de leitura que vêm do documento dele e que o código sustenta:

- **A cadeia é ordenada e se percorre de cima para baixo.** Titular ausente →
  o 2º assume, sem pedir autorização. É o que a carteira chama de sentido de
  dono com continuidade.
- **A Coordenação encerra todas as cadeias.** Por isso `responsavel_atual`
  devolve `None` só quando NINGUÉM da cadeia está preenchido — e a tela trata
  isso como PENDÊNCIA, não como vazio comum: processo sem dono é o defeito que
  a carteira existe para impedir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.processo import AtribuicaoProcesso, FuncaoRH, Processo

CENARIOS = ("C1", "C2")

# Ritmo é a JANELA DE RESPOSTA, não a dificuldade — a legenda da planilha é
# explícita. Guardado aqui para a tela ordenar e explicar; o campo no banco é
# string livre, porque a carteira é revisada por trimestre.
RITMOS: dict[str, str] = {
    "Imediato": "prazo legal, contado em horas",
    "Rápido": "até 2 dias úteis",
    "Curto": "dentro da semana",
    "Médio": "semanas",
    "Médio/Longo": "depende de terceiros",
    "Diário": "todo dia útil",
    "Contínuo": "acompanhamento permanente",
    "Mensal": "fechamento mensal",
}
# Os que não podem esperar: a tela destaca, e o alerta de cadeia curta pesa mais
# neles. A CAT tem prazo legal contado em HORAS — o próprio documento manda
# acompanhar de perto.
RITMOS_CRITICOS = ("Imediato", "Rápido")


def normalizar(texto: str | None) -> str:
    """Compara nome de função/pessoa ignorando acento, caixa e espaço extra.

    A planilha é digitada à mão e revisada por trimestre: "Láysa Costa" e
    "Laysa  Costa" são a mesma pessoa, e casar por igualdade literal criaria
    função duplicada a cada importação — o erro que a v1.96 já pagou com
    cargos e jornadas do Tirvu.
    """
    base = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", base)


# Titulares que NÃO são uma pessoa: na planilha do Bruno, os processos 9.1
# (Conferência do Módulo de Demandas) e 9.2 (Gestão de Canais) têm como titular
# a "Escala diária (rodízio)" — eles giram entre a equipe por dia útil, e é
# assim de propósito. Marcá-los é o que evita a tela acusar "processo sem dono"
# num caso que está CERTO: alarme falso ensina a ignorar o alarme, e aí o
# processo realmente órfão passa junto.
MARCADORES_RODIZIO = ("escala", "rodizio", "rodízio")


def eh_rodizio(nome: str | None) -> bool:
    chave = normalizar(nome)
    return any(m in chave for m in MARCADORES_RODIZIO)


@dataclass
class Elo:
    """Um degrau da cadeia, já resolvido para a pessoa que ocupa a função."""
    posicao: int
    funcao_id: str
    funcao: str
    pessoa: str | None
    vago: bool


def cadeia(db: Session, processo_id, cenario: str = "C1") -> list[Elo]:
    """A cadeia de responsabilidade, do titular ao último apoio."""
    linhas = db.scalars(
        select(AtribuicaoProcesso)
        .where(AtribuicaoProcesso.processo_id == processo_id,
               AtribuicaoProcesso.cenario == cenario)
        .order_by(AtribuicaoProcesso.posicao)).all()
    funcoes = {f.id: f for f in db.scalars(select(FuncaoRH)).all()}
    saida = []
    for a in linhas:
        f = funcoes.get(a.funcao_id)
        if f is None:
            continue
        saida.append(Elo(posicao=a.posicao, funcao_id=str(f.id), funcao=f.nome,
                         pessoa=f.pessoa_nome, vago=not (f.pessoa_nome or "").strip()))
    return saida


def responsavel_atual(elos: list[Elo]) -> Elo | None:
    """Quem responde AGORA: o primeiro da cadeia cuja função tem gente.

    É a função que dá sentido ao módulo. Se o titular saiu (função vaga), a
    resposta é o 2º — automaticamente, sem ninguém redistribuir carteira. Se
    NINGUÉM da cadeia tem gente, devolve `None`, e isso é uma pendência que a
    tela precisa gritar: processo sem dono não avisa sozinho quando deixa de
    ser feito.
    """
    for e in elos:
        if not e.vago:
            return e
    return None


def dump_processo(db: Session, p: Processo, cenario: str = "C1",
                  todas: dict | None = None) -> dict:
    elos = cadeia(db, p.id, cenario)
    atual = responsavel_atual(elos)
    titular = elos[0] if elos else None
    return {
        "id": str(p.id), "codigo": p.codigo, "fase": p.fase, "nome": p.nome,
        "ritmo": p.ritmo, "ritmo_ajuda": RITMOS.get(p.ritmo or "", ""),
        "critico": (p.ritmo or "") in RITMOS_CRITICOS,
        "observacao": p.observacao, "ativo": p.ativo,
        "aprovadores": p.aprovadores or [],
        "consultados": p.consultados or [],
        "informados": p.informados or [],
        "cadeia": [{"posicao": e.posicao, "funcao_id": e.funcao_id,
                    "funcao": e.funcao, "pessoa": e.pessoa, "vago": e.vago}
                   for e in elos],
        "titular": titular.funcao if titular else None,
        "titular_pessoa": titular.pessoa if titular else None,
        # Quem responde HOJE — pode ser diferente do titular, e a tela mostra
        # essa diferença: é o caso "a titular saiu, quem assume?".
        "responsavel": atual.pessoa if atual else None,
        "responsavel_funcao": atual.funcao if atual else None,
        "assumido": bool(atual and titular and atual.posicao != titular.posicao),
        # As duas pendências que a carteira existe para impedir.
        "rodizio": bool(titular and eh_rodizio(titular.funcao)),
        # Rodízio NÃO é processo sem dono: ele tem dono por escala, e acusá-lo
        # aqui produziria alarme falso — que ensina a ignorar o alarme.
        "sem_dono": atual is None and not (titular and eh_rodizio(titular.funcao)),
        "cadeia_curta": len(elos) < 2,
    }


def carga_por_funcao(db: Session, cenario: str = "C1") -> list[dict]:
    """Quantos processos cada função possui e apoia — o dimensionamento.

    Titular e apoio contam SEPARADOS de propósito: são cargas de natureza
    diferente. Quem é dono responde por prazo e resultado; quem apoia entra
    quando chamado. Somar os dois num número só esconderia justamente o que a
    Coordenação precisa ver ao redistribuir.
    """
    funcoes = db.scalars(select(FuncaoRH).order_by(FuncaoRH.ordem, FuncaoRH.nome)).all()
    atrib = db.scalars(select(AtribuicaoProcesso)
                       .where(AtribuicaoProcesso.cenario == cenario)).all()
    ativos = {p.id for p in db.scalars(select(Processo).where(Processo.ativo)).all()}

    dono: dict = {}
    apoio: dict = {}
    for a in atrib:
        if a.processo_id not in ativos:
            continue
        alvo = dono if a.posicao == 1 else apoio
        alvo[a.funcao_id] = alvo.get(a.funcao_id, 0) + 1

    return [{
        "id": str(f.id), "funcao": f.nome, "pessoa": f.pessoa_nome,
        "vaga_aberta": not (f.pessoa_nome or "").strip(),
        "descricao": f.descricao,
        "dono": dono.get(f.id, 0), "apoio": apoio.get(f.id, 0),
        "total": dono.get(f.id, 0) + apoio.get(f.id, 0),
    } for f in funcoes if f.ativa]


def alertas(db: Session, cenario: str = "C1") -> list[dict]:
    """O que está errado na carteira AGORA — o que a planilha não consegue dizer.

    Três coisas, em ordem de gravidade. Todas são silenciosas por natureza:
    processo sem dono não reclama, cadeia curta só aparece no dia da ausência, e
    função vaga se descobre quando alguém procura o responsável.
    """
    achados = []
    processos = db.scalars(
        select(Processo).where(Processo.ativo)
        .order_by(Processo.ordem, Processo.codigo)).all()

    for p in processos:
        elos = cadeia(db, p.id, cenario)
        titular = elos[0] if elos else None
        if titular and eh_rodizio(titular.funcao):
            continue   # gira por escala: tem dono todo dia, só não é fixo
        if not elos:
            # Processo que não existe NESTE cenário — o 9.3 (Indicadores) só
            # aparece no C2, porque nasce com o Analista Jr. Não é falha da
            # carteira: é a carteira dizendo o que muda quando a vaga for
            # preenchida, que é justamente a pergunta de dimensionamento.
            achados.append({
                "tipo": "fora_do_cenario", "gravidade": "baixa",
                "codigo": p.codigo, "processo": p.nome,
                "texto": f"Não tem cadeia no cenário {cenario} — está previsto "
                         "para o outro cenário de efetivo.",
            })
        elif responsavel_atual(elos) is None:
            achados.append({
                "tipo": "sem_dono", "gravidade": "alta",
                "codigo": p.codigo, "processo": p.nome,
                "texto": "Ninguém da cadeia está ocupado — este processo não "
                         "tem quem responda por ele.",
            })
        elif len(elos) < 2:
            achados.append({
                "tipo": "cadeia_curta",
                # Ritmo crítico pesa mais: a CAT tem prazo em HORAS, e ficar
                # sem substituto nela é diferente de ficar num processo mensal.
                "gravidade": "alta" if (p.ritmo or "") in RITMOS_CRITICOS else "media",
                "codigo": p.codigo, "processo": p.nome,
                "texto": "Só uma pessoa na cadeia: se ela faltar, ninguém "
                         "assume." + (f" O ritmo é {p.ritmo}." if p.ritmo else ""),
            })

    for f in db.scalars(select(FuncaoRH).where(FuncaoRH.ativa)).all():
        if (f.pessoa_nome or "").strip() or eh_rodizio(f.nome):
            continue
        qtd = db.scalar(select(AtribuicaoProcesso).where(
            AtribuicaoProcesso.funcao_id == f.id,
            AtribuicaoProcesso.cenario == cenario,
            AtribuicaoProcesso.posicao == 1)) is not None
        achados.append({
            "tipo": "funcao_vaga", "gravidade": "media" if qtd else "baixa",
            "codigo": None, "processo": f.nome,
            "texto": f"A função “{f.nome}” está sem ninguém."
                     + (" Ela é titular de processos, que passaram ao apoio."
                        if qtd else ""),
        })
    return achados
