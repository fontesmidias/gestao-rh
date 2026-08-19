"""Regras do ciclo MENSAL do Reembolso-Creche.

Fica fora das rotas de propósito (regra de entrada do projeto: módulo novo nasce
com o serviço separado da rota) e é PURO no que dá — quem decide o que é
pendência, qual é o valor e se a competência é retroativa não precisa de HTTP
para ser testado.

O que o Jurídico definiu (e-mail do Dr. Lucas, 18/08/2026) e vale como regra:

* **Um comprovante por filho e por mês** — nota fiscal se a creche for PJ,
  declaração de quitação se o cuidador for PF.
* **Corte no dia 25.** O que se entrega até lá é a despesa do mês ANTERIOR.
* Pagamento até o **5º dia útil do mês seguinte** ao fechamento — número
  diferente do corte, e os dois convivem no mesmo processo.
"""

from __future__ import annotations

from datetime import date

# Dia de corte definido pelo Jurídico. É o PADRÃO: cada benefício tem o seu em
# `BeneficioCreche.dia_entrega_mensal`, editável pelo RH (individual e em massa).
# ⚠️ Até 18/08/2026 o padrão era 5 — que é o prazo de PAGAMENTO (5º dia útil),
# não o de entrega. Quem foi ativado antes disso recebeu por e-mail a instrução
# de enviar até o dia 5.
DIA_CORTE_PADRAO = 25

_MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro")


def competencia_anterior(hoje: date) -> tuple[int, int]:
    """O mês cuja despesa se comprova AGORA: o anterior ao corrente.

    Quem entrega em 25/09 está comprovando a despesa de agosto — o serviço já
    foi prestado. Pedir o mês corrente exigiria comprovar despesa que ainda não
    terminou de acontecer.
    """
    return (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)


def rotulo(ano: int, mes: int) -> str:
    """`(2026, 8)` → `agosto/2026`."""
    return f"{_MESES[mes - 1]}/{ano}" if 1 <= mes <= 12 else f"{mes}/{ano}"


def valida(ano: int, mes: int, hoje: date) -> str | None:
    """Devolve o motivo da recusa, ou `None` se a competência é aceitável.

    Recusa o FUTURO: não existe despesa comprovada de um mês que não terminou, e
    aceitar deixaria alguém 'adiantar' comprovantes. O passado NÃO é recusado
    aqui — competência antiga é caso legítimo (a pessoa atrasou, o RH está
    regularizando) e, quando anterior à vigência do contrato, quem decide é o RH
    (ver `anterior_a_vigencia`).
    """
    if not (1 <= mes <= 12):
        return "mes_invalido"
    if (ano, mes) > (hoje.year, hoje.month):
        return "competencia_futura"
    if (ano, mes) == (hoje.year, hoje.month):
        return "competencia_em_curso"
    if ano < 2026:
        # a IN é de 2026; antes disso não havia benefício a comprovar
        return "anterior_a_norma"
    return None


def em_atraso(ano: int, mes: int, dia_corte: int, hoje: date) -> bool:
    """A competência `(ano, mes)` já passou do corte e ainda não foi entregue?

    O corte do mês seguinte é o prazo: a despesa de agosto vence no dia 25 de
    setembro. Chamado só para competência SEM comprovante — quem já entregou
    não está em atraso.
    """
    venc_ano, venc_mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    try:
        vencimento = date(venc_ano, venc_mes, min(max(dia_corte, 1), 28))
    except ValueError:                       # defensivo; o dia já vem limitado
        vencimento = date(venc_ano, venc_mes, 25)
    return hoje > vencimento


def dias_para_o_corte(dia_corte: int, hoje: date) -> int:
    """Quantos dias faltam para o próximo corte (0 = é hoje).

    É o número que decide o lembrete: o RH configura avisar 1, 2, N dias antes.
    """
    dia = min(max(dia_corte, 1), 28)
    if hoje.day <= dia:
        return dia - hoje.day
    prox_ano, prox_mes = (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
    return (date(prox_ano, prox_mes, dia) - hoje).days


def centavos(texto: str | None) -> int | None:
    """`"R$ 1.234,56"` → `123456`. `None` quando não dá para interpretar.

    **Nunca devolve 0 para texto ilegível** — zero entraria calado na soma do
    reembolso e o total sairia menor sem nada acusar (é a regra que o
    `_valor_unitario` do creche já segue, e a razão de ela existir).
    """
    if texto is None:
        return None
    limpo = str(texto).strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if not limpo:
        return None
    # separador decimal é o ÚLTIMO símbolo quando há dois dígitos depois dele;
    # o ponto de milhar some. "1.234,56" e "1234.56" chegam ao mesmo lugar.
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return int(round(float(limpo) * 100))
    except ValueError:
        return None


def reais(centavos_valor: int | None) -> str | None:
    """`123456` → `R$ 1.234,56`."""
    if centavos_valor is None:
        return None
    return f"R$ {centavos_valor / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def valor_reembolsavel(despesa_centavos: int | None,
                       teto_centavos: int | None) -> int | None:
    """O que se paga: **o menor** entre a despesa comprovada e o teto do posto.

    Decisão do Bruno (2026-08-18): o `valor_reembolso_creche` do posto é TETO,
    não valor fixo. Comprovou R$ 400 num posto de R$ 526,64 → reembolsa R$ 400.

    Sem despesa não há o que reembolsar (`None`, não zero: são coisas
    diferentes — zero afirma que a despesa foi nula). Sem teto configurado,
    devolve a despesa: inventar teto aqui pagaria menos do que o contrato prevê,
    calado.
    """
    if despesa_centavos is None:
        return None
    if teto_centavos is None:
        return despesa_centavos
    return min(despesa_centavos, teto_centavos)
