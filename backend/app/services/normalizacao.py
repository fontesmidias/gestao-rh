"""Normalização de qualquer envio (foto, PDF, Word) para PDF, com validações
inteligentes: nitidez (foto borrada é recusada na hora) e data do comprovante
de residência (OCR; mais de 90 dias é recusado)."""

import io
import logging
import re
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

import img2pdf
from PIL import Image, ImageChops, ImageFilter, ImageStat
from pypdf import PdfReader

log = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024
_EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp"}
_EXT_WORD = {".doc", ".docx", ".odt", ".rtf"}

# Energia mínima de detalhe (variância das altas frequências) para considerar a
# foto legível. Calibrado com fotos reais: nítidas ficam bem acima de 100;
# borradas de leve ~5-15; lisas/ilegíveis ~0. Conservador para não gerar falso
# positivo em documento com fundo claro.
NITIDEZ_MINIMA = 3.0
VALIDADE_COMPROVANTE_DIAS = 90


class ArquivoInvalido(Exception):
    def __init__(self, codigo: str):
        self.codigo = codigo
        super().__init__(codigo)


def normalizar_para_pdf(nome_arquivo: str, dados: bytes) -> tuple[bytes, int]:
    """Devolve (pdf_bytes, paginas). Levanta ArquivoInvalido com código legível."""
    if len(dados) == 0:
        raise ArquivoInvalido("arquivo_vazio")
    if len(dados) > MAX_BYTES:
        raise ArquivoInvalido("arquivo_grande_demais")

    ext = Path(nome_arquivo.lower()).suffix

    if ext == ".pdf":
        pdf = dados
    elif ext in _EXT_IMAGEM:
        pdf = _imagem_para_pdf(dados)
    elif ext in _EXT_WORD:
        pdf = _word_para_pdf(ext, dados)
    else:
        raise ArquivoInvalido("formato_nao_suportado")

    try:
        paginas = len(PdfReader(io.BytesIO(pdf)).pages)
    except Exception as exc:
        raise ArquivoInvalido("pdf_corrompido") from exc
    if paginas == 0:
        raise ArquivoInvalido("pdf_sem_paginas")
    return pdf, paginas


def combinar_pdfs(pdfs: list[bytes]) -> tuple[bytes, int]:
    """Junta vários PDFs (frente/verso, páginas de certidão…) em um só.
    Devolve (pdf_combinado, total_de_paginas)."""
    if len(pdfs) == 1:
        return pdfs[0], len(PdfReader(io.BytesIO(pdfs[0])).pages)
    from pypdf import PdfWriter
    escritor = PdfWriter()
    total = 0
    for pdf in pdfs:
        leitor = PdfReader(io.BytesIO(pdf))
        for pagina in leitor.pages:
            escritor.add_page(pagina)
            total += 1
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue(), total


def _nitidez(img: Image.Image) -> float:
    """Energia de detalhe da imagem: diferença entre a imagem e ela mesma
    desfocada. Foto tremida/borrada ou totalmente lisa tem energia ~0."""
    g = img.convert("L")
    g.thumbnail((1200, 1200))
    detalhe = ImageChops.difference(g, g.filter(ImageFilter.GaussianBlur(2)))
    return ImageStat.Stat(detalhe).var[0]


def _imagem_para_pdf(dados: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except Exception as exc:
        raise ArquivoInvalido("imagem_invalida") from exc
    if img.width < 300 or img.height < 300:
        raise ArquivoInvalido("imagem_pequena_demais")
    if _nitidez(img) < NITIDEZ_MINIMA:
        raise ArquivoInvalido("imagem_borrada")
    # Reencoda como JPEG (remove transparência/HEIC) antes do img2pdf.
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return img2pdf.convert(buf.getvalue())


# ---------- Data do comprovante de residência (OCR) ----------

_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5,
          "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
          "novembro": 11, "dezembro": 12}
_RE_DDMMAAAA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")
_RE_MES_EXTENSO = re.compile(
    r"\b(?:(\d{1,2})\s*(?:de)?\s*)?(" + "|".join(_MESES) + r")\s*(?:de|/)?\s*(\d{4})\b",
    re.IGNORECASE)


def _datas_no_texto(texto: str) -> list[date]:
    hoje = date.today()
    datas = []
    for d, m, a in _RE_DDMMAAAA.findall(texto):
        try:
            datas.append(date(int(a), int(m), int(d)))
        except ValueError:
            continue
    for d, mes, a in _RE_MES_EXTENSO.findall(texto.lower()):
        try:
            datas.append(date(int(a), _MESES[mes], int(d or 1)))
        except (ValueError, KeyError):
            continue
    # Só datas plausíveis para um comprovante: nem antigas demais, nem futuras.
    return [x for x in datas if date(hoje.year - 3, 1, 1) <= x <= hoje + timedelta(days=60)]


def _texto_do_envio(ext: str, dados: bytes, pdf: bytes) -> str:
    """Texto do documento: camada de texto do PDF ou OCR da foto (se o
    tesseract estiver instalado; sem ele, a checagem é pulada em silêncio)."""
    if ext == ".pdf":
        try:
            paginas = PdfReader(io.BytesIO(pdf)).pages[:3]
            return "\n".join((p.extract_text() or "") for p in paginas)
        except Exception:
            return ""
    if ext in _EXT_IMAGEM:
        try:
            import pytesseract
            img = Image.open(io.BytesIO(dados))
            img.thumbnail((2000, 2000))
            return pytesseract.image_to_string(img.convert("L"), lang="por")
        except Exception as exc:
            log.warning("OCR indisponível/falhou (%s) — checagem de data pulada.", exc)
            return ""
    return ""


def validar_comprovante_recente(nome_arquivo: str, dados: bytes, pdf: bytes) -> None:
    """Comprovante de residência deve ter no máximo 90 dias. Se nenhuma data for
    encontrada (OCR não leu), não bloqueia — o RH decide na revisão."""
    ext = Path(nome_arquivo.lower()).suffix
    datas = _datas_no_texto(_texto_do_envio(ext, dados, pdf))
    if not datas:
        return
    mais_recente = max(datas)
    if mais_recente < date.today() - timedelta(days=VALIDADE_COMPROVANTE_DIAS):
        raise ArquivoInvalido("comprovante_antigo")


def _word_para_pdf(ext: str, dados: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        origem = Path(tmp) / f"doc{ext}"
        origem.write_bytes(dados)
        resultado = subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(origem)],
            capture_output=True,
            timeout=120,
        )
        destino = origem.with_suffix(".pdf")
        if resultado.returncode != 0 or not destino.exists():
            raise ArquivoInvalido("conversao_word_falhou")
        return destino.read_bytes()
