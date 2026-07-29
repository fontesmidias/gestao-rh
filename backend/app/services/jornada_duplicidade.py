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


def _numeros(s: str) -> list[str]:
    return re.findall(r"\d+", s or "")


def _so_letras(s: str) -> str:
    return re.sub(r"[^A-Z]", "", _canon(s))


def suspeitas(descricoes: list[str], limiar: float = 0.90) -> list[dict]:
    """Pares que MERECEM os olhos do RH — não todo par parecido.

    Medido nos 269 registros reais da planilha de escalas (2026-07-28): o
    limiar de similaridade sozinho devolvia **199 pares, dos quais só 3 eram
    duplicata**. Os outros 196 eram jornadas legitimamente diferentes:

      - 80 pares: mesmo texto, horário diferente ("…13H -16H" x "…13H -17H").
        Uma sai às 16h, a outra às 17h — fundir troca a jornada de alguém.
      - 40 pares: mesmo horário, cliente diferente (CARLTON CENTER x CARLTON
        TOWER, INEP x MME, CFQ x DKP). Prédios e contratos distintos.

    Uma fila 99% ruído é pior que fila nenhuma: o RH pediu "resolver em massa"
    justamente porque não dava para achar o que importava no meio dela — e
    resolver 199 em massa seria o merge cego que este módulo existe para
    impedir.

    Por isso a regra passou a ser ESTRUTURAL, não só de similaridade:

      1. **Números diferentes ⇒ jornadas diferentes.** Horário é o dado que
         distingue turno; um dígito a mais já é outra jornada. Nunca suspeito.
      2. **Mesmos números + letras diferentes ⇒ clientes diferentes.** Também
         não é duplicata (INEP x MME às 7:30 são dois contratos).
      3. Sobra o que é a MESMA coisa escrita de dois jeitos — pontuação,
         espaço, acento, typo. Aí sim o RH decide.

    `limiar` continua aceito para quem quiser afrouxar/apertar a triagem de
    entrada, mas as regras acima é que definem o que sai.
    """
    pares: list[dict] = []
    itens = list(dict.fromkeys(d for d in descricoes if d and d.strip()))
    for i in range(len(itens)):
        for j in range(i + 1, len(itens)):
            a, b = itens[i], itens[j]
            # (1) horário diferente = jornada diferente, sem discussão
            if _numeros(a) != _numeros(b):
                continue
            # (2) mesmo horário mas outro cliente/posto = jornada diferente
            if _so_letras(a) != _so_letras(b):
                continue
            sim = _similaridade(a, b)
            if sim < limiar:
                continue
            pares.append({
                "a": a, "b": b,
                "similaridade": round(sim, 3),
                # iguais depois de normalizar+corrigir typo = duplicata quase
                # certa (só grafia difere); ainda assim o RH confirma.
                "identicas_apos_normalizar": _canon(a) == _canon(b),
            })
    pares.sort(key=lambda p: (-p["identicas_apos_normalizar"], -p["similaridade"]))
    return pares
