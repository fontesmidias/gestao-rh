"""Leitura (OCR) de documentos para SUGERIR o preenchimento do formulário.

Princípios (decisão de projeto, 2026-07-15):
- O OCR sugere; o candidato confere e CONFIRMA — a responsabilidade é dele.
- Falhou a leitura? Nada quebra: devolve menos sugestões (ou nenhuma).
- Nunca sobrescreve o que o candidato já digitou (o front só preenche vazios).
- Muita gente manda a CNH no lugar do RG: os padrões reconhecem os dois e o
  sistema avisa (sem brigar) quando o documento não é o esperado.
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


_RE_CNH_REGISTRO = re.compile(r"REGISTRO\D{0,20}(\d{9,11})")
_RE_CNH_CAT = re.compile(r"CAT\.?\s*(?:HAB\.?)?\s*:?\s*([A-E]{1,2}|ACC)\b")
_RE_TITULO = re.compile(r"\b(\d{4})\s?(\d{4})\s?(\d{4})\b")
_RE_ZONA = re.compile(r"ZONA\s*:?\s*(\d{1,4})")
_RE_SECAO = re.compile(r"SE[ÇC][ÃA]O\s*:?\s*(\d{1,4})")


def detectar_tipo(texto: str) -> str | None:
    """Palpite do tipo de documento a partir do texto lido ('cnh', 'rg',
    'titulo', 'cpf' ou None). Serve para avisar — nunca para bloquear."""
    up = texto.upper()
    if "HABILITA" in up and ("CARTEIRA NACIONAL" in up or "MOTORISTA" in up
                             or "PERMISSÃO" in up or _RE_CNH_CAT.search(up)):
        return "cnh"
    if "TÍTULO" in up and "ELEITOR" in up or ("TITULO" in up and "ELEITOR" in up):
        return "titulo"
    if "REGISTRO GERAL" in up or "CARTEIRA DE IDENTIDADE" in up or "IDENTIDADE" in up:
        return "rg"
    if "CADASTRO DE PESSOAS" in up or "SITUAÇÃO CADASTRAL" in up or "SITUACAO CADASTRAL" in up:
        return "cpf"
    return None


def sugestoes_da_cnh(texto: str) -> dict:
    """A CNH traz quase tudo que o RG traz (CPF, nascimento, filiação, doc de
    identidade com órgão emissor) mais o registro e a categoria."""
    sug = sugestoes_do_rg(texto)
    # O nº de registro da CNH pode confundir com o RG — na dúvida, não sugere RG.
    sug.pop("rg_numero", None)
    up = texto.upper()
    m = _RE_CNH_REGISTRO.search(up)
    if m and m.group(1) != re.sub(r"\D", "", sug.get("cpf", "")):
        sug["cnh_numero"] = m.group(1)
    m = _RE_CNH_CAT.search(up)
    if m:
        sug["cnh_categoria"] = m.group(1)
    return sug


def sugestoes_do_titulo(texto: str) -> dict:
    """Título de eleitor (físico ou e-Título): número, zona e seção."""
    sug: dict = {}
    up = texto.upper()
    for a, b, c in _RE_TITULO.findall(up):
        numero = a + b + c
        if not cpf_valido(numero[:11]):  # evita pescar um CPF por engano
            sug["titulo_eleitor_numero"] = numero
            break
    m = _RE_ZONA.search(up)
    if m:
        sug["titulo_eleitor_zona"] = m.group(1)
    m = _RE_SECAO.search(up)
    if m:
        sug["titulo_eleitor_secao"] = m.group(1)
    return sug


def sugestoes_do_cpf_doc(texto: str) -> dict:
    """Cartão CPF ou comprovante de situação cadastral: CPF e nascimento."""
    sug: dict = {}
    achados = cpfs_no_texto(texto)
    if achados:
        sug["cpf"] = achados[0]
    hoje = date.today()
    datas = [d for d in _datas(texto) if date(1930, 1, 1) <= d <= hoje]
    if datas:
        nascimento = min(datas)
        if nascimento <= date(hoje.year - 14, hoje.month, hoje.day):
            sug["data_nascimento"] = nascimento.isoformat()
    return sug


_RE_CEP_ROTULADO = re.compile(r"CEP\D{0,3}(\d{5})[-.\s]?(\d{3})\b", re.IGNORECASE)
_RE_CEP_HIFEN = re.compile(r"\b(\d{5})-(\d{3})\b")


def sugestoes_do_comprovante(texto: str) -> dict:
    """Comprovante de endereço: o CEP basta — o front busca o resto do
    endereço (rua, bairro, cidade) a partir dele, como já faz na digitação.
    Contas têm números demais (código de barras, nº do cliente), então só
    aceitamos CEP rotulado ('CEP 70000-000') ou no formato com hífen."""
    for regex in (_RE_CEP_ROTULADO, _RE_CEP_HIFEN):
        for a, b in regex.findall(texto):
            cep = a + b
            if cep != "00000000":
                return {"cep": cep}
    return {}


def sugestoes_por_slot(tipo_slot: str, texto: str) -> tuple[dict, str | None]:
    """Dispatcher por tipo de slot do checklist. Devolve (sugestões, tipo
    detectado no texto). No slot do RG aceita e lê também uma CNH — comum de
    acontecer — e o front avisa que o RG mesmo continua pendente."""
    detectado = detectar_tipo(texto)
    if tipo_slot == "rg":
        return (sugestoes_da_cnh(texto) if detectado == "cnh"
                else sugestoes_do_rg(texto)), detectado
    if tipo_slot == "habilitacao_prof":
        return (sugestoes_da_cnh(texto) if detectado in (None, "cnh") else {}), detectado
    if tipo_slot == "cpf_doc":
        return sugestoes_do_cpf_doc(texto), detectado
    if tipo_slot == "titulo_eleitor_doc":
        return sugestoes_do_titulo(texto), detectado
    if tipo_slot == "comp_endereco":
        return sugestoes_do_comprovante(texto), detectado
    return {}, detectado


def cpfs_no_texto(texto: str) -> list[str]:
    """Todos os CPFs com dígito verificador válido encontrados no texto."""
    achados = []
    for g in _RE_CPF.findall(texto):
        cpf = "".join(g)
        if cpf_valido(cpf) and cpf not in achados:
            achados.append(cpf)
    return achados
