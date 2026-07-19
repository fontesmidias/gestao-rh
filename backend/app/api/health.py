from fastapi import APIRouter, Request

from app.core.config import base_url_publica

router = APIRouter(tags=["health"])

# Marcador de versão: muda a cada deploy que precisa ser confirmado no ar.
VERSAO_DEPLOY = "v1.50-callback-https"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "versao": VERSAO_DEPLOY}


@router.get("/diag/callback")
def diag_callback(request: Request) -> dict:
    """Diagnóstico público (sem dados sensíveis): mostra a URL pública que o
    sistema monta e os headers de protocolo que o proxy/Cloudflare enviam.
    Serve para confirmar, no ar, se o callback OAuth sai http ou https."""
    base = base_url_publica(request)
    return {
        "versao": VERSAO_DEPLOY,
        "url_publica_montada": base,
        "callback_m365": f"{base}/api/rh/config/m365/callback",
        "headers_de_protocolo": {
            "host": request.headers.get("host"),
            "x-forwarded-host": request.headers.get("x-forwarded-host"),
            "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
            "cf-visitor": request.headers.get("cf-visitor"),
            "x-forwarded-ssl": request.headers.get("x-forwarded-ssl"),
            "url_scheme_visto": request.url.scheme,
        },
    }
