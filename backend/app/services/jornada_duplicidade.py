"""Detector de DUPLICIDADE suspeita entre jornadas (feedback 2026-07-22).

Só SINALIZA pares parecidos para o RH decidir — NUNCA funde (há ~40 erros de
digitação reais nos dados; merge cego cria associação errada invisível, regra
do CLAUDE.md). "INEP" e "INEP ADM" são clientes iguais mas jornadas DIFERENTES;
"ADICIONAL" e "ADICONAL" são a MESMA com typo — só um humano decide qual é qual.
Por isso devolvemos candidatos ordenados por similaridade, não um veredito.
"""

import re
import unicodedata
from difflib import SequenceMatcher


def _norm(s: str) -> str:
    """Normaliza para comparação: sem acento, MAIÚSCULO, espaços colapsados,
    pontuação de borda removida. NÃO remove palavras (senão fundiria
    INEP/INEP ADM)."""
    s = "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))
    s = s.upper()
    s = re.sub(r"[|.\s]+", " ", s).strip()
    return s


# typos frequentes observados nos dados reais (aplicados só na comparação,
# jamais na descrição gravada)
_TYPOS = {
    "ADICONAL": "ADICIONAL",
    "MINI": "MINUTOS",
    "REDUCAO": "REDUCAO",
}


def _canon(s: str) -> str:
    n = _norm(s)
    for errado, certo in _TYPOS.items():
        n = n.replace(errado, certo)
    return n


def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, _canon(a), _canon(b)).ratio()


def suspeitas(descricoes: list[str], limiar: float = 0.90) -> list[dict]:
    """Recebe as descrições e devolve pares suspeitos (similaridade >= limiar),
    ordenados do mais parecido ao menos. Cada item:
    {a, b, similaridade, identicas_apos_normalizar}. O RH decide."""
    pares: list[dict] = []
    itens = list(dict.fromkeys(d for d in descricoes if d and d.strip()))
    for i in range(len(itens)):
        for j in range(i + 1, len(itens)):
            a, b = itens[i], itens[j]
            sim = _similaridade(a, b)
            if sim >= limiar:
                pares.append({
                    "a": a, "b": b,
                    "similaridade": round(sim, 3),
                    # iguais depois de normalizar+corrigir typo = duplicata quase
                    # certa (só grafia difere); ainda assim o RH confirma.
                    "identicas_apos_normalizar": _canon(a) == _canon(b),
                })
    pares.sort(key=lambda p: (-p["identicas_apos_normalizar"], -p["similaridade"]))
    return pares
