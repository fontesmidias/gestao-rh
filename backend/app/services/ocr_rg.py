"""Leitura (OCR) do RG para SUGERIR o preenchimento do formulário.

Princípios (decisão de projeto, 2026-07-15):
- O OCR sugere; o candidato confere e CONFIRMA — a responsabilidade é dele.
- Falhou a leitura? Nada quebra: devolve menos sugestões (ou nenhuma).
- Nunca sobrescreve o que o candidato já digitou (o front só preenche vazios).
"""

import logging
import re
from datetime import date

from app.services.validacao import cpf_valido

log = logging.getLogger(__name__)

_RE_DATA = re.compile(r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b")
_RE_CPF = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")
_RE_RG = re.compile(r"\b(\d{1,2}\.?\d{3}\.?\d{3})-?(\d|X)?\b")
_RE_ORGAO = re.compile(r"\b(SSP|PC|DETRAN|IFP|ITEP|SEJUSP|SESP|POLITEC)[/\s-]?([A-Z]{2})\b")
_PALAVRAS_NAO_NOME = {"FILIACAO", "FILIAÇÃO", "NATURALIDADE", "DATA", "NASCIMENTO",
                      "REGISTRO", "GERAL", "EXPEDICAO", "EXPEDIÇÃO", "ASSINATURA",
                      "DIRETOR", "VALIDA", "TERRITORIO", "NACIONAL", "CPF", "DOC",
                      "ORIGEM", "COMARCA"}


def _datas(texto: str) -> list[date]:
    datas = []
    for d, m, a in _RE_DATA.findall(texto):
        try:
            datas.append(date(int(a), int(m), int(d)))
        except ValueError:
            continue
    return datas


def _parece_nome(linha: str) -> bool:
    palavras = [p for p in re.split(r"[^A-ZÀ-Ú]", linha.upper()) if len(p) > 1]
    if len(palavras) < 2 or len(palavras) > 7:
        return False
    return not any(p in _PALAVRAS_NAO_NOME for p in palavras)


def sugestoes_do_rg(texto: str) -> dict:
    """Extrai sugestões do texto OCR de um RG. Devolve só o que encontrou."""
    hoje = date.today()
    sug: dict = {}

    # CPF (RGs novos trazem) — só se os dígitos verificadores fecham.
    for g in _RE_CPF.findall(texto):
        cpf = "".join(g)
        if cpf_valido(cpf):
            sug["cpf"] = cpf
            break

    # Datas: nascimento é a mais antiga plausível; expedição, a mais recente.
    datas = [d for d in _datas(texto) if date(1930, 1, 1) <= d <= hoje]
    if datas:
        nascimento = min(datas)
        expedicao = max(datas)
        if nascimento <= date(hoje.year - 14, hoje.month, hoje.day):
            sug["data_nascimento"] = nascimento.isoformat()
        if expedicao != nascimento:
            sug["rg_data_expedicao"] = expedicao.isoformat()

    # Órgão emissor (SSP/DF etc.)
    m = _RE_ORGAO.search(texto.upper())
    if m:
        sug["rg_orgao_emissor"] = f"{m.group(1)}/{m.group(2)}"

    # Número do RG: padrão pontuado perto de "REGISTRO GERAL", ou o primeiro
    # número pontuado que não seja o CPF.
    up = texto.upper()
    trecho = up
    pos = up.find("REGISTRO GERAL")
    if pos == -1:
        pos = up.find("GERAL")
    if pos >= 0:
        trecho = up[pos:pos + 120]
    for m in _RE_RG.finditer(trecho):
        numero = m.group(0).replace(" ", "")
        so_digitos = re.sub(r"\D", "", numero)
        if sug.get("cpf") and so_digitos in sug["cpf"]:
            continue
        if 5 <= len(so_digitos) <= 10:
            sug["rg_numero"] = numero
            break

    # Filiação: linhas de nome logo após a palavra FILIAÇÃO.
    linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
    idx = next((i for i, ln in enumerate(linhas)
                if "FILIA" in ln.upper()), None)
    if idx is not None:
        nomes = [ln for ln in linhas[idx:idx + 5][1:] if _parece_nome(ln)][:2]
        # Padrão histórico do RG: pai na primeira linha, mãe na segunda.
        if len(nomes) == 2:
            sug["nome_pai"], sug["nome_mae"] = nomes[0].title(), nomes[1].title()
        elif len(nomes) == 1:
            sug["nome_mae"] = nomes[0].title()

    return sug


def cpfs_no_texto(texto: str) -> list[str]:
    """Todos os CPFs com dígito verificador válido encontrados no texto."""
    achados = []
    for g in _RE_CPF.findall(texto):
        cpf = "".join(g)
        if cpf_valido(cpf) and cpf not in achados:
            achados.append(cpf)
    return achados
