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


def normalizar_para_pdf(nome_arquivo: str, dados: bytes,
                        rotulo: str | None = None) -> tuple[bytes, int]:
    """Devolve (pdf_bytes, paginas). Levanta ArquivoInvalido com código legível.
    Fotos ganham página A4 no papel timbrado com o `rotulo` do documento;
    PDFs de terceiros (CTPS, certidões…) seguem intactos — não se altera
    documento emitido por órgão."""
    if len(dados) == 0:
        raise ArquivoInvalido("arquivo_vazio")
    if len(dados) > MAX_BYTES:
        raise ArquivoInvalido("arquivo_grande_demais")

    ext = Path(nome_arquivo.lower()).suffix

    if ext == ".pdf":
        # Decisão do RH: todo PDF também vai para o papel timbrado da empresa,
        # com cada página reduzida para caber no corpo A4. Se as artes faltarem
        # (ou algo falhar), o PDF segue intacto.
        timbrado = _pdf_para_timbrado(dados, rotulo)
        pdf = timbrado if timbrado is not None else dados
    elif ext in _EXT_IMAGEM:
        pdf = _imagem_para_pdf(dados, rotulo)
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


def _imagem_para_pdf(dados: bytes, rotulo: str | None = None) -> bytes:
    try:
        img = Image.open(io.BytesIO(dados))
        img.load()
    except Exception as exc:
        raise ArquivoInvalido("imagem_invalida") from exc
    if img.width < 300 or img.height < 300:
        raise ArquivoInvalido("imagem_pequena_demais")
    if _nitidez(img) < NITIDEZ_MINIMA:
        raise ArquivoInvalido("imagem_borrada")
    # Reencoda como JPEG (remove transparência/HEIC).
    buf = io.BytesIO()
    img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=88)
    pagina = _pagina_timbrada(buf.getvalue(), img.width, img.height, rotulo)
    if pagina is not None:
        return pagina
    return img2pdf.convert(buf.getvalue())


_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_TIMBRADO_TOPO = str(_ASSETS / "timbrado-topo.png")
_TIMBRADO_RODAPE = str(_ASSETS / "timbrado-rodape.jpg")
_TIMBRADO_MARCA = str(_ASSETS / "timbrado-marca.png")


# Área útil do corpo da página timbrada (mm): abaixo do cabeçalho, acima do
# rodapé. Documentos são reduzidos para caber aqui, sem distorção.
_CORPO_X, _CORPO_LARG = 12.0, 186.0
_CORPO_Y, _CORPO_ALT = 30.0, 238.0


def _tem_artes_timbrado() -> bool:
    return Path(_TIMBRADO_TOPO).exists() and Path(_TIMBRADO_RODAPE).exists()


def _desenhar_timbrado(pdf, rotulo: str | None) -> None:
    """Desenha, numa página A4 já adicionada ao FPDF, a marca d'água + arte de
    canto (à direita) + rodapé + rótulo e data centralizados. Reutilizado pela
    página de foto e pelo fundo dos PDFs."""
    try:  # marca d'água ao fundo (o conteúdo, opaco, fica por cima)
        larg = 104
        pdf.image(_TIMBRADO_MARCA, x=210 - larg, y=(297 - larg * 662 / 296) / 2, w=larg)
    except Exception:
        pass
    pdf.image(_TIMBRADO_TOPO, x=210 - 34, y=0, w=34)
    pdf.image(_TIMBRADO_RODAPE, x=0, y=297 - 23, w=210)
    pdf.set_y(9)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(23, 26, 60)
    titulo = (rotulo or "documento").upper().replace("_", " ")
    pdf.set_x(0)
    pdf.cell(210, 6, titulo.encode("latin-1", "replace").decode("latin-1"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(110, 120, 112)
    pdf.set_x(0)
    pdf.cell(210, 5, f"Recebido pelo Portal de Admissao em {date.today():%d/%m/%Y}",
             align="C", new_x="LMARGIN", new_y="NEXT")


def _pagina_timbrada(jpeg: bytes, w_px: int, h_px: int,
                     rotulo: str | None) -> bytes | None:
    """Foto de documento vira página A4 no papel timbrado da empresa, com o
    nome do documento e a data de recebimento — dossiê 'organizadinho'.
    Sem as artes no disco, devolve None e o fluxo antigo (img2pdf) assume."""
    if not _tem_artes_timbrado():
        return None
    try:
        from fpdf import FPDF
        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(False)
        pdf.add_page()
        _desenhar_timbrado(pdf, rotulo)
        # Foto reduzida proporcionalmente para caber na área útil, sem distorcer.
        escala = min(_CORPO_LARG / w_px, _CORPO_ALT / h_px)
        w_mm, h_mm = w_px * escala, h_px * escala
        pdf.image(io.BytesIO(jpeg),
                  x=(210 - w_mm) / 2, y=_CORPO_Y + (_CORPO_ALT - h_mm) / 2, w=w_mm, h=h_mm)
        return bytes(pdf.output())
    except Exception:
        return None  # qualquer surpresa: página simples, nunca bloqueia o envio


def _pdf_para_timbrado(pdf_bytes: bytes, rotulo: str | None) -> bytes | None:
    """Cada página do PDF original é reduzida proporcionalmente e centralizada
    no corpo de uma página A4 timbrada da empresa (decisão do RH: todo PDF vai
    para o papel timbrado). Preserva as características do original — apenas
    reduz para caber. Devolve None se as artes não estiverem no disco (aí o PDF
    segue intacto)."""
    if not _tem_artes_timbrado():
        return None
    try:
        from fpdf import FPDF
        from pypdf import PdfWriter, Transformation
        from pypdf._page import PageObject

        base = FPDF(format="A4")
        base.set_auto_page_break(False)
        base.add_page()
        _desenhar_timbrado(base, rotulo)
        fundo = PdfReader(io.BytesIO(bytes(base.output()))).pages[0]

        mm = 2.834645  # pontos por mm
        a4_w, a4_h = 210 * mm, 297 * mm
        bx, bw = _CORPO_X * mm, _CORPO_LARG * mm
        by, bh = _CORPO_Y * mm, _CORPO_ALT * mm

        writer = PdfWriter()
        for pagina in PdfReader(io.BytesIO(pdf_bytes)).pages:
            pw = float(pagina.mediabox.width) or 1.0
            ph = float(pagina.mediabox.height) or 1.0
            escala = min(bw / pw, bh / ph)
            dx = bx + (bw - pw * escala) / 2
            dy = by + (bh - ph * escala) / 2
            folha = PageObject.create_blank_page(width=a4_w, height=a4_h)
            folha.merge_page(fundo)  # timbrado ao fundo
            folha.merge_transformed_page(
                pagina, Transformation().scale(escala).translate(dx, dy))
            writer.add_page(folha)
        saida = io.BytesIO()
        writer.write(saida)
        return saida.getvalue()
    except Exception:
        log.exception("Falha ao aplicar timbrado no PDF; mantendo o original")
        return None


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


_MIME_IMAGEM = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp"}


def _texto_do_envio(ext: str, dados: bytes, pdf: bytes) -> str:
    """Texto do documento. Ordem (decisão do RH, 2026-07-16): OCR com IA
    (Mistral) SEMPRE em primeiro lugar quando há chave; depois a camada de
    texto do PDF; por fim o Tesseract local. Qualquer degrau indisponível cai
    para o seguinte em silêncio."""
    from app.services.ocr_ia import texto_via_mistral

    if ext == ".pdf":
        # Lê SEMPRE o PDF original (`dados`), não a versão já colocada no papel
        # timbrado: o merge/transform da página degrada a camada de texto e
        # confunde o OCR (isso quebrava a checagem de data do comprovante).
        texto_ia = texto_via_mistral(dados, "application/pdf")
        if texto_ia:
            return texto_ia
        try:
            paginas = PdfReader(io.BytesIO(dados)).pages[:3]
            return "\n".join((p.extract_text() or "") for p in paginas)
        except Exception:
            return ""
    if ext in _EXT_IMAGEM:
        texto_ia = texto_via_mistral(dados, _MIME_IMAGEM.get(ext, "image/jpeg"))
        if texto_ia:
            return texto_ia
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
