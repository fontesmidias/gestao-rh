"""Parser PROPONENTE de jornadas (feedback 2026-07-22).

Lê a descrição de texto livre da jornada (coluna P da planilha de colaboradores,
ex.: "INEP ADM - 2ª A 6ª - 08H - 12H - 13H - 17H") e PROPÕE os campos
estruturados (escala, horários, turno, intrajornada, cargo). É só sugestão: o
RH confirma/corrige. NUNCA grava sozinho, NUNCA funde descrições parecidas
(regra dos ~40 erros de digitação nos dados reais — merge cego cria associação
errada invisível). Validado contra as 270 descrições reais: ~79% saem com
escala + 4/8 horários completos; o resto o RH revisa.
"""

import re
import unicodedata


def _deacc(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# cargos típicos embutidos na descrição (ordem = prioridade de match)
_CARGOS = [
    ("brigadista", ("BRIGAD",)),
    ("motorista", ("MOTORISTA",)),
    ("agente de portaria", ("AGP", "AG. PORT", "AGENTE DE PORT")),
    ("ASG", ("ASG",)),
    ("copeiragem", ("COPEIRAGEM", "COPA", "COPEIR")),
    ("audiovisual", ("AUDIOVISUAL",)),
    ("ferista", ("FERISTA",)),
]


def _escala(u: str, original: str) -> str | None:
    """u = texto sem acento, MAIÚSCULO, sem espaços."""
    if "12X36" in u:
        return "12x36"
    if "5X2" in u:
        return "5x2"
    if "2AA6A" in u or "SEGUNDAASEXTA" in u or "SEG.ASEX" in u or "SEGASEX" in u \
            or "2ª A 6ª" in original:
        return "seg-sex"
    if "2AA5A" in u or "2ª A 5ª" in original:
        return "seg-qui+sex"
    if u.startswith("INTERMITENTE"):
        return "intermitente"
    return None


def _horarios(txt: str) -> list[str]:
    """Extrai horas na ordem: aceita 08H, 7:30H, 17:48H, 07:00 (sem H), 13H30.
    Retorna "HH:MM"."""
    out: list[str] = []
    for h, m in re.findall(r'\b(\d{1,2})[:hH]?(\d{2})?\s*H?\b', txt):
        hi = int(h)
        mi = int(m) if m else 0
        if 0 <= hi <= 23 and 0 <= mi <= 59:
            out.append(f"{hi:02d}:{mi:02d}")
    return out


def _cliente(txt: str) -> str:
    return re.split(r'\s*-\s*', txt.strip())[0] if txt else ""


def _intra_obs(u: str) -> str | None:
    """Devolve o trecho de intrajornada achado ("15 MINUTOS", "REDUÇÃO", "INTRA",
    "10 MINI") para o RH confirmar; None se não houver indício."""
    for chave in ("MINUTOS", "REDU", "INTRA", "MINI"):
        m = re.search(r'([\w ]*' + chave + r'[\w ]*)', u)
        if m:
            return m.group(1).strip()[:60]
    return None


def propor(descricao: str) -> dict:
    """Proposta estruturada + confiança. Campos podem vir None quando o parser
    não tem certeza — é o sinal para o RH preencher à mão."""
    txt = (descricao or "").strip()
    u = _deacc(txt).upper()
    u_semespaco = u.replace(" ", "")

    escala = _escala(u_semespaco, txt)
    horas = _horarios(txt)
    composta = "|" in txt  # sexta/sábado diferente => 2 blocos
    noturno = "NOTURNO" in u
    intra_obs = _intra_obs(u)

    cargo = None
    for nome, marcadores in _CARGOS:
        if any(mk in u for mk in marcadores):
            cargo = nome
            break

    # bloco principal = os 4 primeiros horários; secundário = o resto (texto)
    principal = horas[:4]
    bloco_sec = None
    if composta:
        partes = txt.split("|", 1)
        bloco_sec = partes[1].strip(" |")[:150] if len(partes) > 1 else None

    campo = lambda i: principal[i] if i < len(principal) else None

    # confiança: alta se tem escala + 4 horários limpos
    completo = escala is not None and len(principal) == 4
    confianca = "alta" if completo else ("media" if (escala or principal) else "baixa")

    return {
        "cliente": _cliente(txt),
        "escala": escala,
        "hora_entrada": campo(0),
        "saida_almoco": campo(1),
        "volta_almoco": campo(2),
        "hora_saida": campo(3),
        "bloco_secundario": bloco_sec,
        "turno": "noturno" if noturno else "diurno",
        "adicional_noturno": noturno,
        "tem_intrajornada": intra_obs is not None,
        "intrajornada_obs": intra_obs,
        "cargo_relacionado": cargo,
        "confianca": confianca,
    }
