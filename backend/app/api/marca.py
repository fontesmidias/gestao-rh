"""Identidade visual da empresa (Configurações → Identidade visual): nome,
razão social, CNPJ, endereço, contato, logo e favicon. Desvincula o sistema de
uma empresa específica sem chumbar nada."""

import uuid

from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     UploadFile)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.config_dinamica import gravar_config
from app.services.marca import dados_empresa, salvar_dados

router = APIRouter(tags=["marca"])

_TIPOS_IMG = {"image/png", "image/jpeg", "image/webp", "image/svg+xml",
              "image/x-icon", "image/vnd.microsoft.icon"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB por imagem


@router.get("/rh/marca", dependencies=[Depends(requer_rh)])
def ver_marca(db: Session = Depends(get_db)) -> dict:
    d = dados_empresa(db)
    return {**{k: d[k] for k in d if not k.endswith("_key")},
            "tem_logo": bool(d["logo_key"]), "tem_favicon": bool(d["favicon_key"])}


class MarcaIn(BaseModel):
    empresa_nome: str | None = None
    empresa_razao: str | None = None
    empresa_cnpj: str | None = None
    empresa_endereco: str | None = None
    empresa_contato: str | None = None


@router.put("/rh/marca")
def salvar_marca(payload: MarcaIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    salvar_dados(db, payload.model_dump(exclude_none=True))
    registrar(db, "marca_atualizada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_marca(db)


def _upload_img(db: Session, arquivo: UploadFile, chave_config: str, prefixo: str) -> str:
    if arquivo.content_type not in _TIPOS_IMG:
        raise HTTPException(status_code=422, detail="formato_invalido")
    dados = arquivo.file.read()
    if len(dados) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="arquivo_grande_demais")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
           "image/svg+xml": "svg", "image/x-icon": "ico",
           "image/vnd.microsoft.icon": "ico"}.get(arquivo.content_type, "png")
    key = f"marca/{prefixo}-{uuid.uuid4().hex[:8]}.{ext}"
    storage.salvar(key, dados, arquivo.content_type)
    gravar_config(db, {chave_config: key})
    db.commit()
    return key


@router.post("/rh/marca/logo")
def upload_logo(arquivo: UploadFile, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    _upload_img(db, arquivo, "empresa_logo_key", "logo")
    registrar(db, "marca_logo_atualizada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"ok": True}


@router.post("/rh/marca/favicon")
def upload_favicon(arquivo: UploadFile, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    _upload_img(db, arquivo, "empresa_favicon_key", "favicon")
    registrar(db, "marca_favicon_atualizada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"ok": True}


# --- Servir a logo/favicon (PÚBLICO: aparecem no painel e nos e-mails) -------


@router.get("/marca/logo")
def servir_logo(db: Session = Depends(get_db)) -> Response:
    key = dados_empresa(db)["logo_key"]
    if not key:
        raise HTTPException(status_code=404, detail="sem_logo")
    return _servir(key)


@router.get("/marca/favicon")
def servir_favicon(db: Session = Depends(get_db)) -> Response:
    key = dados_empresa(db)["favicon_key"]
    if not key:
        raise HTTPException(status_code=404, detail="sem_favicon")
    return _servir(key)


def _servir(key: str) -> Response:
    tipo = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
            "svg": "image/svg+xml", "ico": "image/x-icon"}.get(key.rsplit(".", 1)[-1], "image/png")
    try:
        dados = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="nao_encontrado")
    return Response(content=dados, media_type=tipo,
                    headers={"Cache-Control": "public, max-age=300"})
