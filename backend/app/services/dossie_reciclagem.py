"""Dossiê de reciclagem: um PDF por colaborador para a entidade formadora.

O Bruno decidiu (2026-07-22): **um arquivo por pessoa**, não os documentos
soltos. A clínica abre `dossie-joao-paulo-lima.pdf` e tem tudo — documento com
foto, certificado de formação e atestado de saúde, nessa ordem.

Reusa `_adicionar_em_a4` do dossiê de admissão: cada página entra
redimensionada e centrada em A4, então foto de celular e PDF de scanner saem
com o mesmo tamanho.
"""

import io
import logging

from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.models.candidato import Candidato
from app.models.desenvolvimento import RegistroDesenvolvimento
from app.services import storage
from app.services.dossie import _adicionar_em_a4

log = logging.getLogger(__name__)

# Ordem em que a clínica espera os documentos (a mesma da lista do Bruno).
ORDEM_PAPEIS = ("identidade", "certificado_formacao", "certificado_reciclagem",
                "aso", "outro")
_EXT_IMAGEM = {"jpg", "jpeg", "png", "webp", "heic", "bmp", "tif", "tiff"}


def _imagem_para_pdf(dados: bytes) -> bytes | None:
    """Foto do celular vira página de PDF. Converte para RGB (PNG com canal
    alfa e HEIC quebrariam o save direto)."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(dados))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((2000, 2000))
        buf = io.BytesIO()
        img.save(buf, "PDF", resolution=150)
        return buf.getvalue()
    except Exception:
        log.warning("Imagem ilegível ao montar o dossiê", exc_info=True)
        return None


def gerar(db: Session, registro: RegistroDesenvolvimento) -> bytes:
    """PDF único com os documentos do registro, na ordem que a clínica espera.

    Documento ilegível é PULADO com aviso no log em vez de derrubar a geração:
    o RH precisa do dossiê dos outros, e a pendência já é sinalizada antes do
    envio por `pendencias_do_dossie`.
    """
    writer = PdfWriter()
    arquivos = sorted(
        registro.arquivos,
        key=lambda a: (ORDEM_PAPEIS.index(a.papel)
                       if a.papel in ORDEM_PAPEIS else len(ORDEM_PAPEIS)))
    for arq in arquivos:
        try:
            dados = storage.ler(arq.key)
        except Exception:
            log.warning("Arquivo %s indisponível no MinIO", arq.key)
            continue
        ext = arq.key.rsplit(".", 1)[-1].lower()
        if ext in _EXT_IMAGEM:
            dados = _imagem_para_pdf(dados)
            if dados is None:
                continue
        elif ext != "pdf":
            log.info("Formato %s não entra no dossiê (%s)", ext, arq.key)
            continue
        try:
            _adicionar_em_a4(writer, dados)
        except Exception:
            log.warning("PDF ilegível: %s", arq.key, exc_info=True)
            continue

    if not writer.pages:
        # Sem página nenhuma o PDF sairia corrompido; melhor falhar alto.
        raise ValueError("dossie_vazio")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def nome_arquivo(col: Candidato) -> str:
    """`dossie-joao-paulo-lima.pdf` — passa pelo slug da casa (o nome é texto
    livre digitado pelo RH: path traversal)."""
    from app.services.export_planilha import slug
    return f"dossie-{slug(col.nome_completo)}.pdf"
