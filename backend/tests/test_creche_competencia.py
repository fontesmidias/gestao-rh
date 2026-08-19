"""Regras do ciclo mensal do Reembolso-Creche (`services/creche_competencia.py`).

Stdlib pura, sem banco: as regras aqui decidem DINHEIRO (o que se reembolsa) e
PRAZO (o que está em atraso, quando lembrar), e precisam reprovar no CI antes de
qualquer coisa subir.

O que este teste protege, em uma frase cada:

* o teto do posto NÃO pode virar valor fixo — pagar o teto quando a despesa foi
  menor é pagar acima do gasto real, em folha;
* valor ilegível NÃO pode virar zero — zero entra calado na soma e o total sai
  menor sem nada acusar;
* a virada de ano tem que funcionar — janeiro comprova dezembro do ano anterior,
  e o vencimento de dezembro cai em janeiro seguinte.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.creche_competencia import (  # noqa: E402
    DIA_CORTE_PADRAO, centavos, competencia_anterior, dias_para_o_corte,
    em_atraso, reais, rotulo, valida, valor_reembolsavel)

falhas = []


def conferir(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


print("1. o corte é o do Jurídico (dia 25), não o prazo de pagamento")
# ⚠️ O padrão era 5 — que é o 5º dia útil do PAGAMENTO, número diferente do
# corte de ENVIO. Os dois convivem no processo e significam coisas opostas.
conferir(DIA_CORTE_PADRAO == 25, "DIA_CORTE_PADRAO é 25")

print("2. a competência que se comprova é a ANTERIOR (o serviço já foi prestado)")
conferir(competencia_anterior(date(2026, 9, 15)) == (2026, 8),
         "em setembro comprova-se agosto")
conferir(competencia_anterior(date(2027, 1, 10)) == (2026, 12),
         "em janeiro comprova-se dezembro DO ANO ANTERIOR")
conferir(rotulo(2026, 8) == "agosto/2026", "rótulo legível da competência")

print("3. futuro é recusado; passado NÃO é (atraso e regularização são legítimos)")
hoje = date(2026, 9, 15)
conferir(valida(2026, 8, hoje) is None, "agosto/2026 é aceita em setembro")
conferir(valida(2026, 9, hoje) == "competencia_em_curso",
         "o mês corrente é recusado — a despesa ainda não terminou")
conferir(valida(2026, 10, hoje) == "competencia_futura",
         "mês futuro é recusado")
conferir(valida(2025, 12, hoje) == "anterior_a_norma",
         "antes de 2026 não havia benefício a comprovar")
conferir(valida(2026, 13, hoje) == "mes_invalido", "mês fora de 1..12")
conferir(valida(2026, 3, hoje) is None,
         "competência antiga é ACEITA (atraso/regularização é caso legítimo)")

print("4. atraso mede contra o corte do mês SEGUINTE")
conferir(em_atraso(2026, 8, 25, date(2026, 9, 20)) is False,
         "agosto ainda no prazo em 20/09")
conferir(em_atraso(2026, 8, 25, date(2026, 9, 25)) is False,
         "no próprio dia do corte ainda está no prazo")
conferir(em_atraso(2026, 8, 25, date(2026, 9, 26)) is True,
         "agosto em atraso a partir de 26/09")
conferir(em_atraso(2026, 12, 25, date(2027, 1, 26)) is True,
         "dezembro vence em JANEIRO do ano seguinte (virada de ano)")

print("5. dias para o corte — é o número que dispara o lembrete")
conferir(dias_para_o_corte(25, date(2026, 9, 20)) == 5, "faltam 5 dias")
conferir(dias_para_o_corte(25, date(2026, 9, 25)) == 0, "o corte é hoje")
conferir(dias_para_o_corte(25, date(2026, 9, 26)) == 29,
         "passado o corte, conta para o do mês seguinte")
conferir(dias_para_o_corte(25, date(2026, 12, 28)) == 28,
         "de dezembro conta para janeiro (virada de ano)")

print("6. dinheiro: nunca zero por engano")
conferir(centavos("R$ 526,64") == 52664, "formato do sistema")
conferir(centavos("1.234,56") == 123456, "com separador de milhar")
conferir(centavos("1234.56") == 123456, "com ponto decimal")
conferir(centavos("400") == 40000, "inteiro sem centavos")
conferir(centavos("R$ 0,00") == 0, "zero DIGITADO é zero de verdade")
# ⚠️ o que separa "a pessoa digitou zero" de "não deu para ler" — tratar
# ilegível como zero faria o total sair menor sem nada acusar
conferir(centavos("abc") is None, "texto ilegível é None, NUNCA zero")
conferir(centavos("") is None and centavos(None) is None, "vazio é None")
conferir(reais(52664) == "R$ 526,64", "volta para o formato de tela")
conferir(reais(123456) == "R$ 1.234,56", "com separador de milhar")

print("7. o valor do posto é TETO, não valor fixo (decisão do Bruno, 18/08/2026)")
teto = 52664
conferir(valor_reembolsavel(40000, teto) == 40000,
         "despesa MENOR que o teto: paga a despesa (não o teto)")
conferir(valor_reembolsavel(60000, teto) == 52664,
         "despesa MAIOR que o teto: paga o teto")
conferir(valor_reembolsavel(teto, teto) == teto, "despesa igual ao teto")
conferir(valor_reembolsavel(None, teto) is None,
         "sem despesa não há reembolso — None, não zero")
conferir(valor_reembolsavel(40000, None) == 40000,
         "sem teto configurado, paga a despesa (inventar teto pagaria a menos)")

print()
if falhas:
    print(f"test_creche_competencia: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("test_creche_competencia: OK")
