"""Import do export de ponto do Tirvu (Onda C — contexto para a avaliação).

Lê o `.xlsx` de ponto eletrônico e agrega a frequência por pessoa/período. O
resultado é CONTEXTO para o avaliador — nunca nota (decisão do Bruno).

Armadilhas dos DADOS REAIS (não hipóteses — estão nas 431 linhas da amostra),
todas tratadas aqui:
  1. NÃO há coluna de CPF: casa por MATRÍCULA, normalizando zeros à esquerda
     dos dois lados (a planilha tem "003035" e "3035" para a mesma pessoa).
  2. `00:00` com marcação de entrada é registro INCOMPLETO (esqueceu a saída),
     NÃO falta. Contado à parte.
  3. Há dia sem batida nenhuma e com horas apuradas: a fonte de verdade é
     `Horas Trabalhadas`, não as batidas. Não se deduz presença dos horários.
  4. Geolocalização e foto (lat/long/URL) NÃO são lidas — desproporcional para
     avaliação (LGPD). Só as colunas de apuração entram.

O leitor é o `_ler_linhas_xlsx` (zip+XML) de `postos.py`: openpyxl quebra nas
planilhas do Tirvu (stylesheet inválido).
"""

import re
from datetime import date, datetime

# Colunas de apuração, na ordem fixa do export (as 13 primeiras). As demais
# (batidas, lat/long, foto) são ignoradas de propósito.
COL_COMPETENCIA = 1
COL_DIA = 2
COL_NOME = 3
COL_MATRICULA = 4
COL_SITUACAO = 9
COL_CARGA_PREVISTA = 10
COL_HORAS_TRAB = 11
# a 1ª coluna de MARCAÇÃO (Entrada 1 · Hora) — só para distinguir falta de
# registro incompleto, nunca para apurar horas
COL_ENTRADA_1 = 13


def matricula_norm(m: str | None) -> str:
    """Só dígitos, sem zeros à esquerda — casa "003035" com "3035"."""
    d = re.sub(r"\D", "", m or "")
    return d.lstrip("0") or d       # tudo-zero vira "0", não vazio


def _min_de_hora(txt) -> int:
    """"09:17" -> 557 minutos. Aceita a 1ª ocorrência (a célula às vezes tem
    dois horários, ex. "10:17 07:00")."""
    m = re.search(r"(\d{1,3}):(\d{2})", str(txt or ""))
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def _data(txt) -> date | None:
    m = re.search(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", str(txt or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def agregar(dados_xlsx: bytes) -> list[dict]:
    """Devolve um resumo por (matrícula) com o período abrangido e a apuração.

    Cada item: matricula, nome, periodo_inicio/fim, minutos_trabalhados/
    previstos, faltas, incompletos, dias_abaixo/acima, detalhe[].
    """
    from app.api.postos import _ler_linhas_xlsx
    linhas = _ler_linhas_xlsx(dados_xlsx)
    if len(linhas) < 3:
        return []

    por_pessoa: dict[str, dict] = {}
    for linha in linhas[2:]:                      # dados começam na linha 2
        if len(linha) <= COL_HORAS_TRAB:
            continue
        mat = matricula_norm(linha[COL_MATRICULA])
        nome = (linha[COL_NOME] or "").strip()
        if not mat and not nome:
            continue
        chave = mat or f"nome:{nome.lower()}"
        d = _data(linha[COL_COMPETENCIA])
        situacao = (linha[COL_SITUACAO] or "").strip()
        trab = _min_de_hora(linha[COL_HORAS_TRAB])
        prev = _min_de_hora(linha[COL_CARGA_PREVISTA])
        tem_entrada = bool(re.search(r"\d{1,2}:\d{2}",
                                     str(linha[COL_ENTRADA_1] if len(linha) > COL_ENTRADA_1 else "")))

        # A distinção que evita a injustiça:
        #   - 0h COM entrada = INCOMPLETO (esqueceu a saída), não falta
        #   - 0h SEM entrada = FALTA de verdade
        incompleto = (trab == 0 and tem_entrada)
        falta = (trab == 0 and not tem_entrada and prev > 0)

        p = por_pessoa.setdefault(chave, {
            "matricula": linha[COL_MATRICULA] or "", "nome": nome,
            "datas": [], "min_trab": 0, "min_prev": 0,
            "faltas": 0, "incompletos": 0, "abaixo": 0, "acima": 0,
            "detalhe": []})
        if not p["nome"] and nome:
            p["nome"] = nome
        if d:
            p["datas"].append(d)
        p["min_trab"] += trab
        p["min_prev"] += prev
        if incompleto:
            p["incompletos"] += 1
        elif falta:
            p["faltas"] += 1
        if "Abaixo" in situacao:
            p["abaixo"] += 1
        elif "Acima" in situacao:
            p["acima"] += 1
        p["detalhe"].append({
            "data": d.isoformat() if d else None,
            "situacao": situacao,
            "minutos": trab, "previsto": prev,
            "incompleto": incompleto, "falta": falta})

    resumos = []
    for p in por_pessoa.values():
        datas = sorted(x for x in p["datas"] if x)
        if not datas:
            continue
        resumos.append({
            "matricula": p["matricula"], "nome": p["nome"],
            "periodo_inicio": datas[0], "periodo_fim": datas[-1],
            "dias_com_registro": len(p["detalhe"]),
            "minutos_trabalhados": p["min_trab"],
            "minutos_previstos": p["min_prev"],
            "faltas": p["faltas"], "incompletos": p["incompletos"],
            "dias_abaixo": p["abaixo"], "dias_acima": p["acima"],
            "detalhe": p["detalhe"]})
    return resumos


def fmt_horas(minutos: int) -> str:
    """780 -> "13h00". Para a tela, mais legível que minutos."""
    return f"{minutos // 60}h{minutos % 60:02d}"
