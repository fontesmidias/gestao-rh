"""Normalização de qualquer envio (foto, PDF, Word) para PDF.

Regras de validação barata feitas aqui (formato, tamanho, imagem minúscula);
validações inteligentes (OCR, nitidez) ficam para a v1.1.
"""

import io
import subprocess
import tempfile
from pathlib import Path

import img2pdf
from PIL import Image
from pypdf import PdfReader

MAX_BYTES = 50 * 1024 * 1024
_EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp"}
_EXT_WORD = {".doc", ".docx", ".odt", ".rtf"}


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


def _imagem_para_pdf(dados: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except Exception as exc:
        raise ArquivoInvalido("imagem_invalida") from exc
    if img.width < 300 or img.height < 300:
        raise ArquivoInvalido("imagem_pequena_demais")
    # Reencoda como JPEG (remove transparência/HEIC) antes do img2pdf.
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return img2pdf.convert(buf.getvalue())


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
