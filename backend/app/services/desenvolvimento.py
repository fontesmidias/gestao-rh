"""Regras do Cadastro de Desenvolvimento (Onda B).

Concentra o que NÃO pode ficar espalhado pelas rotas: herança do prazo de
validade, cálculo do vencimento, e a decisão de quem pode ser aprovado em lote.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidato import Candidato
from app.models.desenvolvimento import (PrazoValidade, RegistroDesenvolvimento,
                                        StatusRegistro, TipoDesenvolvimento)

# Cargos que compõem a brigada (decisão do Bruno, 2026-07-22). Comparados
# normalizados — o `cargo_funcao` é texto livre digitado pelo RH.
CARGOS_BRIGADA = ("chefe de brigada", "brigadista", "bombeiro civil",
                  "bombeiro lider")


def _norm(texto: str | None) -> str:
    """Minúsculas sem acento — para comparar cargo digitado à mão."""
    import unicodedata
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def e_da_brigada(cargo: str | None) -> bool:
    """O cargo é um dos quatro da brigada? Usa `in` e não igualdade porque o
    cargo real vem com variação ("BOMBEIRO CIVIL DIURNO", "Brigadista Líder")."""
    c = _norm(cargo)
    return bool(c) and any(b in c for b in CARGOS_BRIGADA)


def meses_validade_de(db: Session, tipo: TipoDesenvolvimento,
                      colaborador: Candidato | None) -> int | None:
    """Prazo de validade aplicável, com herança em TRÊS níveis — o mais
    específico vence:

        posto (do colaborador) > cargo (do colaborador) > tipo (padrão)

    Pedido do Bruno: "customizável por posto, ou cargo, ou qualquer outra
    coisa". Sem colaborador (ex.: simulação na tela do tipo), cai no padrão.
    """
    if not tipo.exige_validade:
        return None
    if colaborador is not None:
        prazos = db.scalars(select(PrazoValidade).where(
            PrazoValidade.tipo_id == tipo.id)).all()
        # 1) posto — o mais específico
        if colaborador.posto_servico_id:
            for p in prazos:
                if p.posto_id == colaborador.posto_servico_id:
                    return p.meses_validade
        # 2) cargo
        cargo = _norm(colaborador.cargo_funcao)
        if cargo:
            for p in prazos:
                if p.cargo and _norm(p.cargo) == cargo:
                    return p.meses_validade
    # 3) padrão do tipo
    return tipo.meses_validade


def calcular_validade(concluido_em: date | None, meses: int | None) -> date | None:
    """Vencimento = conclusão + N meses. Sem biblioteca de calendário: soma
    meses "na mão" e trata o estouro de dia (31/01 + 1 mês = 28/02)."""
    if concluido_em is None or not meses:
        return None
    ano = concluido_em.year + (concluido_em.month - 1 + meses) // 12
    mes = (concluido_em.month - 1 + meses) % 12 + 1
    dia = concluido_em.day
    while dia > 0:
        try:
            return date(ano, mes, dia)
        except ValueError:
            dia -= 1  # 31 → 30 → 29 → 28
    return None


def dias_para_vencer(validade: date | None, hoje: date | None = None) -> int | None:
    """Dias que faltam (negativo = já venceu). None se não tem validade."""
    if validade is None:
        return None
    return (validade - (hoje or date.today())).days


def situacao_validade(registro: RegistroDesenvolvimento,
                      hoje: date | None = None) -> str:
    """Rótulo do estado da certificação, para dash e filtro:
    `sem_validade` | `valido` | `a_vencer` | `vencido`.

    `a_vencer` usa a antecedência do TIPO (`aviso_dias_antes`, 60 por padrão),
    que é o mesmo prazo do e-mail — o que o RH vê no painel é exatamente o que
    dispara o aviso, sem dois números divergentes."""
    dias = dias_para_vencer(registro.validade_ate, hoje)
    if dias is None:
        return "sem_validade"
    if dias < 0:
        return "vencido"
    limite = registro.tipo.aviso_dias_antes if registro.tipo else 60
    return "a_vencer" if dias <= limite else "valido"


def pode_aprovar_em_lote(registro: RegistroDesenvolvimento) -> bool:
    """Só o caso FÁCIL entra na aprovação em massa.

    Documento crítico (brigada, NR) **nunca** entra: um dia alguém aprova 40 de
    uma vez sem olhar e o sistema passa a afirmar que há certificado válido onde
    não há — pior que não ter sistema, porque agora tem gente confiando nele.

    Também exige que os campos que importam estejam preenchidos: aprovar em
    lote um registro sem data de conclusão criaria certificação sem validade
    calculável.
    """
    if registro.status != StatusRegistro.pendente:
        return False
    tipo = registro.tipo
    if tipo is None or tipo.critico:
        return False
    if not registro.titulo:
        return False
    if tipo.exige_validade and registro.concluido_em is None:
        return False
    return True


def tipos_do_cargo(db: Session, cargo: str | None) -> list[TipoDesenvolvimento]:
    """Tipos que se aplicam a um cargo. `cargos_aplicaveis` vazio = todos."""
    tipos = db.scalars(select(TipoDesenvolvimento).where(
        TipoDesenvolvimento.ativo == True)).all()  # noqa: E712
    c = _norm(cargo)
    saida = []
    for t in tipos:
        alvos = t.cargos_aplicaveis or []
        if not alvos or any(_norm(a) in c or c in _norm(a) for a in alvos if a):
            saida.append(t)
    return saida
