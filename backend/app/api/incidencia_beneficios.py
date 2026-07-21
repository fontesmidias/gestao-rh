"""Importação da planilha de Incidência de Benefícios (RH).

A planilha (`docs/Planilha Incidência de Benefícios_*.xlsx`) tem 2 abas:
- **PÚBLICO**: contratos com órgãos (Cliente | Nº do contrato | Objeto | ... |
  Reembolso creche/Mês | ...).
- **PRIVADO**: clientes privados (Cliente | Objeto | (sem nº) | ... | Reembolso
  creche/Mês | ...).

Ela cumpre dois papéis:
1. **Normaliza o nome do posto** no padrão `CLIENTE - Nº CONTRATO - OBJETO`
   (público) / `CLIENTE - OBJETO` (privado) — o mesmo padrão que futuramente
   atualizará o Tirvu.
2. É a **fonte de elegibilidade ao Reembolso-Creche** por contrato/posto: a
   coluna "Reembolso creche/Mês" define `da_direito_creche` + `valor_reembolso_creche`.

**Equivalência ASSISTIDA (nunca merge cego):** para cada linha o sistema PROPÕE
o posto do Tirvu correspondente (casamento por Cliente/Objeto), com um score, e o
RH CONFIRMA cada uma (ou marca "novo"/"ignorar"). A regra do projeto é explícita:
descrições parecidas NÃO se fundem sozinhas — há ~40 erros de digitação nos dados
reais e um merge silencioso cria associação errada invisível. Casos compostos
(ex.: dois sindicatos numa célula) ficam sinalizados para decisão humana.

Leitura via zip+XML puro (openpyxl quebra com planilhas sujas — armadilha do
projeto). Este módulo lê AS DUAS abas (o `_ler_linhas_xlsx` de `postos.py` lê só
a primeira).
"""

import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import PostoServico
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar

router = APIRouter(tags=["incidencia-beneficios"], dependencies=[Depends(requer_rh)])

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_SEM_VALOR = {"", "nao ha", "não há", "nao há", "não ha", "-", "n/a", "na"}


def _norm(txt: str) -> str:
    """Minúsculo, sem acento, espaços colapsados — para comparar cabeçalhos e
    nomes de cliente/objeto."""
    txt = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", txt).strip().lower()


def _col_para_idx(ref: str) -> int:
    letras = re.match(r"[A-Z]+", ref or "")
    if not letras:
        return 0
    n = 0
    for ch in letras.group(0):
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _ler_abas(conteudo: bytes) -> dict[str, list[list[str]]]:
    """Lê TODAS as abas de um .xlsx como matrizes de strings (zip+XML puro).
    Devolve {nome_da_aba: linhas}. Vazio se inválido."""
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except Exception:
        return {}
    compartilhadas: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in raiz:
            compartilhadas.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    # mapeia nome da aba -> arquivo da worksheet, via workbook.xml + rels
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except Exception:
        return {}
    RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    ns_r = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    rid_para_alvo = {r.get("Id"): r.get("Target") for r in rels.iter(f"{ns_r}Relationship")}
    abas: dict[str, list[list[str]]] = {}
    for sheet in wb.iter(f"{NS}sheet"):
        nome = sheet.get("name") or ""
        rid = sheet.get(f"{RNS}id")
        alvo = rid_para_alvo.get(rid)
        if not alvo:
            continue
        caminho = "xl/" + alvo.lstrip("/") if not alvo.startswith("xl/") else alvo
        if caminho not in z.namelist():
            caminho = "xl/" + alvo.split("/")[-1]
            caminho = next((n for n in z.namelist() if n.endswith(alvo.split("/")[-1])), None)
        if not caminho or caminho not in z.namelist():
            continue
        raiz = ET.fromstring(z.read(caminho))
        linhas: list[list[str]] = []
        for row in raiz.iter(f"{NS}row"):
            celulas: dict[int, str] = {}
            for c in row.findall(f"{NS}c"):
                idx = _col_para_idx(c.get("r", ""))
                tipo = c.get("t")
                v = c.find(f"{NS}v")
                if tipo == "s":
                    texto = compartilhadas[int(v.text)] if v is not None and v.text else ""
                elif tipo == "inlineStr":
                    iss = c.find(f"{NS}is")
                    texto = "".join(t.text or "" for t in iss.iter(f"{NS}t")) if iss is not None else ""
                else:
                    texto = v.text if v is not None else ""
                celulas[idx] = (texto or "").strip()
            largura = (max(celulas) + 1) if celulas else 0
            linhas.append([celulas.get(i, "") for i in range(largura)])
        abas[nome] = linhas
    return abas


def _valor_creche(bruto: str) -> str | None:
    """Normaliza a célula 'Reembolso creche/Mês'. 'NÃO HÁ'/vazio -> None; um
    número -> 'R$ 636,00'. Valores compostos (dois sindicatos) são preservados
    como texto para decisão humana."""
    b = (bruto or "").strip()
    if _norm(b) in _SEM_VALOR:
        return None
    # número simples: aceita 636, 636.9, 636,90, 1.234,56 (milhar com ponto)
    m = re.fullmatch(r"\s*R?\$?\s*(\d{1,3}(?:\.\d{3})*|\d+)(?:[.,](\d{1,2}))?\s*", b)
    if m:
        inteiro = m.group(1).replace(".", "")  # remove separador de milhar
        cents = (m.group(2) or "00").ljust(2, "0")  # '9' -> '90'
        return f"R$ {int(inteiro):,}".replace(",", ".") + f",{cents}"
    # composto/ambíguo: devolve o texto original (o RH decide)
    return b


def _composto(bruto: str) -> bool:
    """Célula com mais de um valor/sindicato — precisa de decisão humana."""
    return bool(re.search(r"\)\s*e\b|;|\/df\).*\/df", _norm(bruto)))


def _nome_normalizado(cliente: str, contrato: str, objeto: str) -> str:
    """Padrão CLIENTE - Nº CONTRATO - OBJETO (público) / CLIENTE - OBJETO
    (privado, sem contrato)."""
    partes = [p.strip() for p in (cliente, contrato, objeto) if (p or "").strip()]
    return " - ".join(partes)


def _achar_col(cabecalho: list[str], *alvos: str) -> int | None:
    norm = [_norm(c) for c in cabecalho]
    for a in alvos:
        na = _norm(a)
        for i, c in enumerate(norm):
            if c == na or (na and na in c):
                return i
    return None


def _parse_linhas(abas: dict[str, list[list[str]]]) -> list[dict]:
    """Extrai as linhas relevantes das abas PÚBLICO/PRIVADO (por nome, tolerante
    a variação). Cada item: cliente, contrato, objeto, creche (bruto+normalizado),
    nome_normalizado, aba, composto."""
    itens: list[dict] = []
    for nome_aba, linhas in abas.items():
        if not linhas:
            continue
        cab = linhas[0]
        ic_cliente = _achar_col(cab, "cliente")
        ic_contrato = _achar_col(cab, "numero do contrato", "número do contrato", "n do contrato")
        ic_objeto = _achar_col(cab, "objeto")
        ic_creche = _achar_col(cab, "reembolso creche/mes", "reembolso creche/mês", "reembolso creche")
        if ic_cliente is None or ic_objeto is None:
            continue  # aba sem o formato esperado
        for bruta in linhas[1:]:
            v = list(bruta) + [""] * (len(cab) - len(bruta))
            cliente = (v[ic_cliente] or "").strip()
            objeto = (v[ic_objeto] or "").strip()
            contrato = (v[ic_contrato] or "").strip() if ic_contrato is not None else ""
            if not cliente and not objeto:
                continue
            creche_bruto = (v[ic_creche] or "").strip() if ic_creche is not None else ""
            itens.append({
                "aba": nome_aba,
                "cliente": cliente,
                "contrato": contrato,
                "objeto": objeto,
                "nome_normalizado": _nome_normalizado(cliente, contrato, objeto),
                "creche_bruto": creche_bruto,
                "creche_valor": _valor_creche(creche_bruto),
                "da_direito_creche": _valor_creche(creche_bruto) is not None,
                "composto": _composto(creche_bruto),
            })
    return itens


def _similaridade(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _propor_equivalencia(item: dict, postos: list[PostoServico]) -> list[dict]:
    """Propõe até 3 postos do Tirvu para a linha, por similaridade de Cliente
    contra nome/sigla/razão social. NUNCA decide sozinho — só ordena candidatos."""
    cliente = item["cliente"]
    ranqueados = []
    for p in postos:
        alvos = [p.nome or "", p.sigla or "", p.razao_social or ""]
        score = max(_similaridade(cliente, a) for a in alvos if a) if any(alvos) else 0.0
        # bônus quando o cliente é prefixo/contido no nome do posto (ANEEL ⊂ ...)
        if cliente and _norm(cliente) in _norm(p.nome or ""):
            score = max(score, 0.9)
        ranqueados.append((score, p))
    ranqueados.sort(key=lambda t: t[0], reverse=True)
    return [{"posto_id": str(p.id), "posto_nome": p.nome, "sigla": p.sigla,
             "score": round(s, 2)}
            for s, p in ranqueados[:3] if s > 0.35]


@router.post("/rh/incidencia/preview")
async def preview(arquivo: UploadFile, db: Session = Depends(get_db)) -> dict:
    """Parseia a planilha e propõe, para cada linha, a equivalência com um posto
    do Tirvu — para o RH revisar e confirmar. Nada é gravado aqui."""
    try:
        conteudo = await arquivo.read()
    finally:
        await arquivo.close()  # descarta o spool em disco (dados sensíveis)
    abas = _ler_abas(conteudo)
    if not abas:
        raise HTTPException(status_code=422, detail="arquivo_invalido")
    itens = _parse_linhas(abas)
    if not itens:
        raise HTTPException(status_code=422, detail="sem_linhas_reconhecidas")
    postos = db.scalars(select(PostoServico).order_by(PostoServico.nome)).all()
    linhas = []
    for i, it in enumerate(itens):
        linhas.append({
            "idx": i,
            **it,
            "sugestoes": _propor_equivalencia(it, postos),
        })
    return {
        "total": len(linhas),
        "com_creche": sum(1 for x in linhas if x["da_direito_creche"]),
        "compostos": sum(1 for x in linhas if x["composto"]),
        "linhas": linhas,
    }


class DecisaoIn(BaseModel):
    # posto de destino: um id existente, ou "novo" (cria), ou "ignorar"
    posto_id: str
    nome_normalizado: str
    da_direito_creche: bool
    valor_reembolso: str | None = None
    contrato_ref: str | None = None


class ConfirmarIn(BaseModel):
    decisoes: list[DecisaoIn]


@router.post("/rh/incidencia/confirmar")
def confirmar(payload: ConfirmarIn, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Aplica as equivalências CONFIRMADAS pelo RH: normaliza o nome do posto,
    grava contrato e a elegibilidade ao reembolso-creche. 'ignorar' não faz nada;
    'novo' cria um posto."""
    criados = atualizados = ignorados = 0
    for d in payload.decisoes:
        if d.posto_id == "ignorar":
            ignorados += 1
            continue
        if d.posto_id == "novo":
            p = PostoServico(nome=d.nome_normalizado.strip())
            db.add(p)
            criados += 1
        else:
            try:
                import uuid
                p = db.get(PostoServico, uuid.UUID(d.posto_id))
            except (ValueError, TypeError):
                p = None
            if p is None:
                continue
            if d.nome_normalizado.strip():
                p.nome = d.nome_normalizado.strip()
            atualizados += 1
        p.da_direito_creche = d.da_direito_creche
        p.valor_reembolso_creche = d.valor_reembolso or None
        if d.contrato_ref:
            p.contrato_ref = d.contrato_ref
    registrar(db, "incidencia_beneficios_aplicada", ator="rh", ator_detalhe=rh.email,
              detalhe={"criados": criados, "atualizados": atualizados,
                       "ignorados": ignorados})
    db.commit()
    return {"criados": criados, "atualizados": atualizados, "ignorados": ignorados}
