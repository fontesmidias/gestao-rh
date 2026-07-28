"""Extração de texto do currículo do talento — reaproveita o OCR/leitura já
existentes no projeto (Mistral OCR com fallback local em ocr_ia.py/
normalizacao.py). Formatos aceitos no Banco de Talentos: pdf, jpg, jpeg, png,
heic, webp, doc, docx (ver CURRICULO_EXTS em api/talentos.py).

Minimização (LGPD art. 6º, III — pertinência ao necessário, feedback do
roundtable 2026-07-27): CPF, RG e telefone são removidos do texto ANTES de
qualquer envio à IA. Nome não é removido — a Groq não tem cláusula de
retenção zero (decisão consciente do Bruno) e o nome é necessário para o RH
identificar o resultado do ranking; a mitigação real é minimizar os
identificadores realmente sensíveis (documentos, contato)."""

import io
import logging
import re

log = logging.getLogger(__name__)

_EXT_IMAGEM = {"jpg", "jpeg", "png", "heic", "webp"}
_MIME_IMAGEM = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
               "heic": "image/heic", "webp": "image/webp"}

# Documento não legível (imagem sem OCR disponível, PDF sem camada de texto e
# sem OCR, DOCX sem LibreOffice) — nunca inventa nota; o chamador decide o que
# fazer (ex.: cair só no filtro estruturado, sem a etapa de IA).
class CurriculoIlegivel(Exception):
    pass


def extrair_texto(dados: bytes, nome_arquivo: str) -> str:
    """Texto do currículo, na melhor extração disponível. Levanta
    CurriculoIlegivel se nada funcionar — o chamador NUNCA deve inventar nota
    para um currículo que não conseguiu ler."""
    ext = (nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else "")

    if ext == "pdf":
        texto = _texto_pdf(dados)
    elif ext in _EXT_IMAGEM:
        texto = _texto_imagem(dados, ext)
    elif ext in ("doc", "docx"):
        texto = _texto_word(dados, ext)
    else:
        texto = ""

    texto = (texto or "").strip()
    if not texto:
        raise CurriculoIlegivel(f"nao_foi_possivel_ler_{ext or 'formato_desconhecido'}")
    return texto


def _texto_pdf(dados: bytes) -> str:
    from app.services.ocr_ia import texto_via_mistral
    texto_ia = texto_via_mistral(dados, "application/pdf")
    if texto_ia:
        return texto_ia
    try:
        from pypdf import PdfReader
        paginas = PdfReader(io.BytesIO(dados)).pages
        return "\n".join((p.extract_text() or "") for p in paginas)
    except Exception:
        return ""


def _texto_imagem(dados: bytes, ext: str) -> str:
    from app.services.ocr_ia import texto_via_mistral
    texto_ia = texto_via_mistral(dados, _MIME_IMAGEM.get(ext, "image/jpeg"))
    if texto_ia:
        return texto_ia
    try:
        import pytesseract
        from PIL import Image

        # importar normalizacao registra o decodificador de HEIC (foto de
        # iPhone) — sem isso, Image.open falha em .heic
        import app.services.normalizacao  # noqa: F401

        img = Image.open(io.BytesIO(dados))
        img.thumbnail((2000, 2000))
        return pytesseract.image_to_string(img.convert("L"), lang="por")
    except Exception as exc:
        log.warning("OCR local indisponível para currículo (%s).", exc)
        return ""


def _texto_word(dados: bytes, ext: str) -> str:
    """DOC/DOCX: converte para PDF via LibreOffice (já usado no projeto para
    o mesmo fim, ver normalizacao.py::_word_para_pdf) e extrai texto do PDF."""
    try:
        from app.services.normalizacao import _word_para_pdf
        pdf_bytes = _word_para_pdf(f".{ext}", dados)
        return _texto_pdf(pdf_bytes)
    except Exception as exc:
        log.warning("Conversão de currículo Word falhou (%s).", exc)
        return ""


# ---------- Minimização de PII antes do envio à IA ----------

_RE_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_RE_RG = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b")
_RE_TELEFONE = re.compile(r"\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4}\b")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_RE_CEP = re.compile(r"\b\d{5}-?\d{3}\b")


def minimizar(texto: str) -> str:
    """Remove CPF, RG, telefone, e-mail e CEP do texto — nenhum desses ajuda
    a IA a avaliar aderência a uma vaga; enviar é gordura, e gordura vaza
    (LGPD art. 6º, III, pertinência ao necessário)."""
    t = _RE_CPF.sub("[CPF removido]", texto)
    t = _RE_RG.sub("[RG removido]", t)
    t = _RE_TELEFONE.sub("[telefone removido]", t)
    t = _RE_EMAIL.sub("[e-mail removido]", t)
    t = _RE_CEP.sub("[CEP removido]", t)
    return t
