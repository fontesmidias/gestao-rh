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
from app.services.marca import (FONTES, dados_empresa, pilha_da_fonte,
                                salvar_dados)

router = APIRouter(tags=["marca"])

# SVG NÃO entra (v2.71). Ele é código, não imagem: um `<script>` dentro do
# arquivo executa quando o navegador o abre, e o `_servir` devolve com
# `media_type: image/svg+xml` numa rota PÚBLICA (`/marca/logo`,
# `/marca/favicon`), no MESMO domínio da aplicação — logo, com acesso à sessão
# de quem estiver logado no painel. É XSS armazenado, e o vetor de entrada é o
# upload de logo, que qualquer usuário do RH faz.
# O `upload_seguro.py` já excluía `.svg` pelo mesmo motivo ("aceitava .exe,
# .svg (que carrega script)"); esta rota nasceu antes dele e ficou de fora.
# PNG/JPG/WebP/ICO cobrem logo e favicon sem essa superfície.
_TIPOS_IMG = {"image/png", "image/jpeg", "image/webp",
              "image/x-icon", "image/vnd.microsoft.icon"}
_MAX_BYTES = 2 * 1024 * 1024  # 2 MB por imagem


@router.get("/rh/marca", dependencies=[Depends(requer_rh)])
def ver_marca(db: Session = Depends(get_db)) -> dict:
    d = dados_empresa(db)
    return {**{k: d[k] for k in d if not k.endswith("_key")},
            "tem_logo": bool(d["logo_key"]), "tem_favicon": bool(d["favicon_key"]),
            # O catálogo vai junto: a tela monta o seletor a partir DELE, nunca de
            # uma lista escrita à mão no JSX — duas listas divergiriam na primeira
            # fonte nova, e a do front é a que a pessoa vê.
            # A `pilha` vai junto para a tela mostrar a PRÉVIA da fonte escolhida
            # antes de salvar — fonte se confere olhando, não lendo o nome.
            "fontes": [{"valor": k, "rotulo": v["rotulo"], "nota": v["nota"],
                        "pilha": v["pilha"]}
                       for k, v in FONTES.items()],
            "fonte_pilha": pilha_da_fonte(d.get("empresa_fonte"))}


class MarcaIn(BaseModel):
    empresa_nome: str | None = None
    empresa_razao: str | None = None
    empresa_cnpj: str | None = None
    empresa_endereco: str | None = None
    empresa_contato: str | None = None
    empresa_fonte: str | None = None


@router.put("/rh/marca")
def salvar_marca(payload: MarcaIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    # SÓ o catálogo entra. Aceitar texto livre deixaria gravar uma pilha CSS
    # arbitrária que vai para o `<style>` de TODA tela, inclusive as públicas —
    # e uma fonte que não existe não dá erro: a tela só fica estranha, sem nada
    # apontando a causa. Mesma trava do documento específico (v2.79).
    if payload.empresa_fonte is not None and payload.empresa_fonte not in FONTES:
        raise HTTPException(status_code=422, detail="fonte_desconhecida")
    salvar_dados(db, payload.model_dump(exclude_none=True))
    registrar(db, "marca_atualizada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return ver_marca(db)


def _upload_img(db: Session, arquivo: UploadFile, chave_config: str, prefixo: str) -> str:
    if arquivo.content_type not in _TIPOS_IMG:
        raise HTTPException(status_code=422, detail="formato_invalido")
    # `close()` no `finally` (v2.71): o Starlette faz spool em disco acima de
    # ~1MB e, sem fechar, o temporário fica no container. Mesma regra do
    # `upload_seguro.py` — aqui não se usa o `ler_upload` porque o teto é
    # próprio (2MB, imagem de marca) e a validação é por content_type.
    try:
        dados = arquivo.file.read()
    finally:
        arquivo.file.close()
    if len(dados) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="arquivo_grande_demais")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
           "image/x-icon": "ico",
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


@router.get("/marca/aparencia")
def aparencia_publica(db: Session = Depends(get_db)) -> dict:
    """A fonte da interface, para QUALQUER tela (v2.85).

    PÚBLICA porque o wizard do candidato não tem login e é a maior parte do uso
    do sistema — deixar a fonte só no `/rh/marca` faria a customização valer no
    painel e não valer para quem está enviando documento pelo celular.

    Devolve a PILHA resolvida, não a chave: quem consome só aplica, e uma chave
    inválida no banco já cai no padrão aqui (`pilha_da_fonte`), em vez de
    chegar ao CSS e deixar a tela sem fonte nenhuma.
    """
    return {"fonte": pilha_da_fonte(dados_empresa(db).get("empresa_fonte"))}


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
    # `svg` saiu do mapa (v2.71) — inclusive na SAÍDA. Tirar só da allowlist de
    # upload não bastaria: logo enviada ANTES da correção continuaria no
    # storage e seguiria sendo servida como `image/svg+xml` executável. Sem a
    # entrada aqui, ela cai no `image/png` do padrão e o navegador não executa
    # o script — a imagem some, o XSS também.
    tipo = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp",
            "ico": "image/x-icon"}.get(key.rsplit(".", 1)[-1], "image/png")
    try:
        dados = storage.ler(key)
    except Exception:
        raise HTTPException(status_code=404, detail="nao_encontrado")
    return Response(content=dados, media_type=tipo,
                    headers={"Cache-Control": "public, max-age=300"})
