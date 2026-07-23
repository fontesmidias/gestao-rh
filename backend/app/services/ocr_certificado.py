"""Extração de campos de CERTIFICADO e de ATESTADO DE SAÚDE (Onda B).

Mesmo princípio do `ocr_rg.py`: **sugere, não decide**. A pessoa confere e
confirma; nada é gravado a partir daqui.

Sobre o atestado de saúde — princípio da NECESSIDADE (LGPD art. 6º, III):
extrai-se **apenas a data do exame e a aptidão**, que é o que a matrícula no
curso exige. **Diagnóstico, CID, exame e queixa NÃO são extraídos** — e há
teste garantindo que um CID no texto não vaza para a sugestão.
"""

import re
from datetime import date

_RE_DATA = re.compile(r"\b(\d{2})[/.-](\d{2})[/.-](\d{2,4})\b")
_RE_CARGA = re.compile(r"\b(\d{1,4})\s*(?:h|hs|horas?)\b", re.IGNORECASE)
# "válido até 22/07/2028", "validade: 07/2028"
_RE_VALIDADE = re.compile(
    r"(?:v[áa]lid[oa]\s*(?:at[ée]|por)?|validade)\s*:?\s*"
    r"(\d{2}[/.-]\d{2}[/.-]\d{2,4})", re.IGNORECASE)
_RE_CONCLUSAO = re.compile(
    r"(?:conclu[íi](?:do|u|s[ãa]o)|realizad[oa]\s*em|emitid[oa]\s*em|"
    r"em)\s*:?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})", re.IGNORECASE)

# Palavras que denunciam o tipo do documento — usadas só para AVISAR quando o
# arquivo parece não ser o que a pessoa disse que era (sem bloquear: o RH
# decide).
_SINAIS = {
    "certificado_formacao": ("brigada", "brigadista", "bombeiro civil",
                             "combate a incendio", "combate a incêndio",
                             "primeiros socorros", "formacao", "formação"),
    "certificado_reciclagem": ("reciclagem", "atualizacao", "atualização",
                               "requalificacao", "requalificação"),
    "aso": ("atestado de saude", "atestado de saúde", "aso", "ocupacional",
            "apto", "inapto", "medico do trabalho", "médico do trabalho"),
    "identidade": ("registro geral", "carteira de identidade",
                   "carteira nacional de habilitacao", "habilitação"),
}


def _datas(texto: str, minimo=date(1990, 1, 1)) -> list[date]:
    """Datas plausíveis no texto, em ordem. Aceita ano com 2 ou 4 dígitos."""
    achadas = []
    for d, m, a in _RE_DATA.findall(texto):
        try:
            ano = int(a)
            if ano < 100:  # "28" -> 2028
                ano += 2000
            achadas.append(date(ano, int(m), int(d)))
        except ValueError:
            continue
    # nada absurdo: nem antes de 1990, nem mais de 15 anos à frente
    teto = date(date.today().year + 15, 12, 31)
    return [x for x in achadas if minimo <= x <= teto]


def _uma_data(padrao: re.Pattern, texto: str) -> date | None:
    m = padrao.search(texto)
    if not m:
        return None
    achadas = _datas(m.group(1))
    return achadas[0] if achadas else None


def detectar_papel(texto: str) -> str | None:
    """Que documento parece ser. Serve para AVISAR divergência, não bloquear —
    muita gente manda o certificado no campo do atestado e vice-versa."""
    up = " ".join((texto or "").lower().split())
    if not up:
        return None
    placar = {papel: sum(1 for s in sinais if s in up)
              for papel, sinais in _SINAIS.items()}
    papel, pontos = max(placar.items(), key=lambda kv: kv[1])
    return papel if pontos else None


def sugestoes_do_certificado(texto: str) -> dict:
    """Campos de um certificado de curso/formação. Devolve só o que achou."""
    sug: dict = {}
    if not texto:
        return sug

    # Instituição: linha com marcador de pessoa jurídica (evita pegar o nome do
    # aluno, que costuma ser a linha em destaque).
    for linha in (l.strip() for l in texto.splitlines() if l.strip()):
        up = linha.upper()
        if any(m in up for m in ("LTDA", "S/A", "S.A", "EIRELI", "ME ",
                                 "CENTRO DE", "ESCOLA", "INSTITUTO",
                                 "TREINAMENTO", "CURSOS", "ACADEMIA")):
            if 5 <= len(linha) <= 120:
                sug["instituicao"] = " ".join(linha.split()).title()
                break

    # Carga horária: pega a MAIOR (o texto costuma ter "8h de teoria, 12h de
    # prática, carga horária total de 20h").
    cargas = [int(h) for h in _RE_CARGA.findall(texto) if 1 <= int(h) <= 2000]
    if cargas:
        sug["carga_horaria"] = f"{max(cargas)}h"

    # Datas: primeiro os padrões rotulados; senão, a mais recente do texto.
    concluido = _uma_data(_RE_CONCLUSAO, texto)
    validade = _uma_data(_RE_VALIDADE, texto)
    todas = _datas(texto)
    hoje = date.today()
    if concluido is None and todas:
        passadas = [d for d in todas if d <= hoje]
        if passadas:
            concluido = max(passadas)
    if validade is None and todas:
        futuras = [d for d in todas if d > hoje]
        if futuras:
            validade = min(futuras)
    if concluido:
        sug["concluido_em"] = concluido.isoformat()
    if validade:
        sug["validade_ate"] = validade.isoformat()

    papel = detectar_papel(texto)
    if papel:
        sug["papel_detectado"] = papel
    return sug


def sugestoes_do_aso(texto: str) -> dict:
    """Campos do Atestado de Saúde Ocupacional.

    **Só data do exame e aptidão** — o mínimo que a matrícula no curso exige.
    Diagnóstico, CID, exames e queixas ficam de fora POR DESENHO: são dado de
    saúde sem necessidade para esta finalidade (LGPD art. 6º, III).
    """
    sug: dict = {}
    if not texto:
        return sug
    up = " ".join(texto.lower().split())

    # Aptidão: "inapto" contém "apto", então a negativa é testada primeiro.
    if "inapto" in up or "não apto" in up or "nao apto" in up:
        sug["aptidao"] = "inapto"
    elif "apto" in up:
        sug["aptidao"] = "apto"

    # Data do exame: a rotulada; senão a mais recente que não seja futura.
    exame = _uma_data(re.compile(
        r"(?:data\s*do\s*exame|exame\s*(?:m[ée]dico)?\s*em|realizado\s*em)"
        r"\s*:?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})", re.IGNORECASE), texto)
    todas = _datas(texto)
    hoje = date.today()
    if exame is None:
        passadas = [d for d in todas if d <= hoje]
        if passadas:
            exame = max(passadas)
    if exame:
        sug["concluido_em"] = exame.isoformat()

    validade = _uma_data(_RE_VALIDADE, texto)
    if validade is None:
        futuras = [d for d in todas if d > hoje]
        if futuras:
            validade = min(futuras)
    if validade:
        sug["validade_ate"] = validade.isoformat()
    return sug


def sugestoes(papel: str, texto: str) -> dict:
    """Ponto de entrada: escolhe o extrator pelo papel do arquivo."""
    if papel == "aso":
        return sugestoes_do_aso(texto)
    if papel == "identidade":
        from app.services.ocr_rg import detectar_tipo, sugestoes_da_cnh, sugestoes_do_rg
        tipo = detectar_tipo(texto)
        return sugestoes_da_cnh(texto) if tipo == "cnh" else sugestoes_do_rg(texto)
    return sugestoes_do_certificado(texto)
