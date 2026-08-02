"""Tempo LÍQUIDO de preenchimento (v2.51).

Pedido do Bruno em 2026-08-02, olhando o card "Tempo médio: 2.590min":

    "o card de tempo deveria refletir o real, de quanto tempo uma pessoa leva
    em média para preencher, mas o tempo LÍQUIDO que ela esteve preenchendo,
    não o tempo que ela iniciou e terminou. Quero o líquido."

A métrica antiga era `dossie_gerado_em - criado_em`: 2.590 min (~43 h) de
calendário, incluindo a pessoa dormindo, trabalhando e esperando o documento
chegar. Não respondia "quanto tempo leva para preencher".

Este teste trava as três decisões do algoritmo, porque todas mudam o número que
o RH vai olhar:

1. **Buraco maior que 30 min não conta** — é a pessoa tendo ido embora, não
   preenchendo devagar. (Mesmo raciocínio do import de ponto: `00:00` com
   entrada é registro incompleto, não jornada de zero hora.)
2. **Sessões diferentes somam** — quem volta no dia seguinte continua a mesma
   pessoa preenchendo o mesmo formulário.
3. **A cauda de sessão tem TETO** — sem ele, quem entra e sai dez vezes ganha
   5 min de crédito por nada (~17% de inflação, medido).

Roda sem BANCO (o teste substitui a consulta por dados em memória), mas
importa `app.services.telemetria`, que puxa SQLAlchemy — por isso **não** entra
no passo de testes estruturais do CI, que roda com Python limpo. Rode à mão ao
mexer no cálculo:

    PYTHONPATH=. .venv/Scripts/python.exe tests/test_tempo_liquido.py
"""

import pathlib
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.telemetria import (  # noqa: E402
    CAUDA_MAX_S, CAUDA_SESSAO_S, GAP_INATIVIDADE_S, tempo_liquido_por_candidato)

FALHAS = []


def checar(ok: bool, descricao: str) -> None:
    print(("  ok    " if ok else "  FALHA ") + descricao)
    if not ok:
        FALHAS.append(descricao)


class _DbFalso:
    """Devolve as linhas prontas — o cálculo não precisa de banco de verdade."""

    def __init__(self, linhas):
        self._linhas = linhas

    def execute(self, _consulta):
        return self

    def all(self):
        return self._linhas


T0 = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
CID = uuid.uuid4()


def linhas(*eventos):
    """(sessao, minuto) -> as tuplas que a consulta devolveria, já ordenadas."""
    return [(CID, f"sess-{s}", T0 + timedelta(minutes=m)) for s, m in eventos]


def calcular(*eventos):
    return tempo_liquido_por_candidato(_DbFalso(linhas(*eventos)), [CID]).get(CID, 0)


print("\n1. Intervalos normais somam")
# 4 intervalos de 2 min = 8 min, + 1 sessão de cauda
r = calcular(("A", 0), ("A", 2), ("A", 4), ("A", 6), ("A", 8))
checar(r == 8 * 60 + CAUDA_SESSAO_S,
       f"5 eventos de 2 em 2 min = 8 min ativos + cauda (obtido: {r}s)")


print("\n2. Buraco de inatividade NÃO conta")
# mesma sessão, mas com 3 horas de intervalo no meio: só 2+1 min entram
r = calcular(("A", 0), ("A", 2), ("A", 182), ("A", 183))
checar(r == 3 * 60 + CAUDA_SESSAO_S,
       f"3h de buraco descartadas, sobram 3 min (obtido: {r}s)")

# o limite exato: 30 min entra, 31 não
dentro = calcular(("A", 0), ("A", GAP_INATIVIDADE_S // 60))
fora = calcular(("A", 0), ("A", GAP_INATIVIDADE_S // 60 + 1))
checar(dentro > fora,
       f"intervalo de {GAP_INATIVIDADE_S // 60} min conta e o de "
       f"{GAP_INATIVIDADE_S // 60 + 1} min não ({dentro}s vs {fora}s)")


print("\n3. Sessões diferentes SOMAM (voltar no dia seguinte conta)")
r = calcular(("A", 0), ("A", 5), ("B", 2000), ("B", 2010))
checar(r == (5 + 10) * 60 + 2 * CAUDA_SESSAO_S,
       f"5 min numa sessão + 10 min noutra = 15 min + 2 caudas (obtido: {r}s)")
# e o intervalo ENTRE sessões nunca entra, por maior que seja
checar(r < 2000 * 60, "o tempo entre as duas visitas não entra na conta")


print("\n4. A cauda tem teto (não premia quem entra e sai muitas vezes)")
muitas = []
for i in range(20):
    muitas += [(f"S{i}", i * 100), (f"S{i}", i * 100 + 1)]
r = calcular(*muitas)
ativo = 20 * 60          # 20 sessões × 1 min
checar(r == ativo + CAUDA_MAX_S,
       f"20 sessões: cauda limitada a {CAUDA_MAX_S}s, não {20 * CAUDA_SESSAO_S}s "
       f"(obtido: {r}s)")


print("\n5. Quem não tem telemetria fica FORA da média, não entra como zero")
vazio = tempo_liquido_por_candidato(_DbFalso([]), [CID])
checar(vazio == {}, "sem eventos, o candidato não aparece no resultado")
checar(tempo_liquido_por_candidato(_DbFalso([]), []) == {},
       "lista vazia de candidatos não consulta nada")


print("\n6. A ordem dos eventos não inventa tempo negativo")
# a consulta ordena, mas se dois eventos tiverem o mesmo instante o delta é 0
r = calcular(("A", 5), ("A", 5), ("A", 7))
checar(r == 2 * 60 + CAUDA_SESSAO_S,
       f"eventos simultâneos não somam nada (obtido: {r}s)")


print()
if FALHAS:
    print(f"test_tempo_liquido: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_tempo_liquido: OK")
