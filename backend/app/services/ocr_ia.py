"""OCR assistido por IA (Mistral OCR) com fallback local.

Regras de segurança (mesa-redonda, 2026-07-15):
- A chave fica na config dinâmica (painel), nunca em log.
- Telemetria registra apenas tipo, hash SHA-256 e tamanho — NUNCA o conteúdo.
- Qualquer falha (sem chave, timeout, quota) devolve None e o Tesseract local
  assume — o OCR com IA melhora quando existe, mas nunca vira dependência.
- O aviso de privacidade do candidato menciona a leitura assistida por IA.
"""

import base64
import hashlib
import logging

import httpx

from app.core.db import SessionLocal

log = logging.getLogger(__name__)
telemetria = logging.getLogger("telemetria")

_URL = "https://api.mistral.ai/v1/ocr"
_MODELO = "mistral-ocr-latest"
_TIMEOUT = 30.0


def chave_mistral(db=None) -> str | None:
    from app.services.config_dinamica import ler_config
    if db is not None:
        return ler_config(db, ("mistral_api_key",)).get("mistral_api_key") or None
    with SessionLocal() as sessao:
        return ler_config(sessao, ("mistral_api_key",)).get("mistral_api_key") or None


def texto_via_mistral(dados: bytes, mime: str,
                      chave: str | None = None) -> str | None:
    """Texto (markdown) lido pela API de OCR da Mistral, ou None para o
    chamador cair no OCR local. `mime`: image/jpeg, image/png, application/pdf."""
    chave = chave or chave_mistral()
    if not chave:
        return None
    b64 = base64.b64encode(dados).decode()
    if mime == "application/pdf":
        documento = {"type": "document_url",
                     "document_url": f"data:{mime};base64,{b64}"}
    else:
        documento = {"type": "image_url",
                     "image_url": f"data:{mime};base64,{b64}"}
    try:
        r = httpx.post(
            _URL,
            headers={"Authorization": f"Bearer {chave}"},
            json={"model": _MODELO, "document": documento},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        paginas = r.json().get("pages", [])
        texto = "\n".join(p.get("markdown", "") for p in paginas)
        telemetria.info(
            "ocr_ia provedor=mistral mime=%s sha256=%s bytes=%s paginas=%s ok=1",
            mime, hashlib.sha256(dados).hexdigest()[:16], len(dados), len(paginas))
        return texto or None
    except Exception as exc:
        # Sem stack no log comum: motivo curto, hash, e o fallback assume.
        telemetria.info(
            "ocr_ia provedor=mistral mime=%s sha256=%s bytes=%s ok=0 motivo=%s",
            mime, hashlib.sha256(dados).hexdigest()[:16], len(dados),
            type(exc).__name__)
        log.warning("Mistral OCR indisponível (%s) — usando OCR local.",
                    type(exc).__name__)
        return None


def testar_mistral(chave: str) -> str:
    """Valida a chave com uma imagem sintética. Devolve o texto lido ou
    levanta RuntimeError com mensagem legível para o painel."""
    import io

    from PIL import Image, ImageDraw
    img = Image.new("RGB", (640, 200), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 80), "TESTE PORTAL ADMISSAO 2026", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    try:
        texto = texto_via_mistral(buf.getvalue(), "image/png", chave=chave)
    except Exception as exc:  # pragma: no cover - texto_via_mistral não levanta
        raise RuntimeError(str(exc)) from exc
    if texto is None:
        raise RuntimeError("A API da Mistral não respondeu ou recusou a chave. "
                           "Confira a chave em console.mistral.ai → API Keys.")
    return texto
