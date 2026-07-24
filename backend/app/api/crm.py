"""Mini-CRM do RH: anotações e tags que acompanham a pessoa (talento+candidato)
por todo o ciclo de vida. Ver models/crm.py e services/crm.py.

- Tags: catálogo com CRUD (usado na Configuração) + marcar/desmarcar na pessoa.
- Anotações: texto livre + autor (snapshot) + data + anexo opcional no MinIO.
- Tudo restrito ao RH (comunicação interna). O front lê pela PESSOA, passando
  talento_id OU candidato_id — o serviço junta os dois lados.

Armadilha de rotas: as rotas de catálogo de tags (`/rh/crm/tags...`) vêm ANTES
das de pessoa; e a paramétrica `/tags/{tag_id}` fica por último para o literal
não virar UUID inválido."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.crm import Anotacao, PessoaTag, Tag
from app.models.usuario_rh import UsuarioRH
from app.services import crm, storage
from app.services.auditoria import registrar

router = APIRouter(tags=["crm"], dependencies=[Depends(requer_rh)])

ANEXO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ANEXO_EXTS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "doc", "docx", "txt", "xlsx"}
ANEXO_CT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "heic": "image/heic", "webp": "image/webp", "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class TagIn(BaseModel):
    nome: str
    cor: str | None = None
    ativo: bool | None = None


class AnotacaoIn(BaseModel):
    talento_id: uuid.UUID | None = None
    candidato_id: uuid.UUID | None = None
    texto: str


class MarcarTagIn(BaseModel):
    tag_id: uuid.UUID
    talento_id: uuid.UUID | None = None
    candidato_id: uuid.UUID | None = None


def _escopo_ou_422(talento_id, candidato_id) -> None:
    if talento_id is None and candidato_id is None:
        raise HTTPException(status_code=422, detail="pessoa_obrigatoria")


# ---------- Catálogo de tags (Configuração) ----------

@router.get("/rh/crm/tags")
def listar_tags(incluir_inativas: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    q = select(Tag).order_by(Tag.nome)
    if not incluir_inativas:
        q = q.where(Tag.ativo.is_(True))
    return [crm.dump_tag(t) for t in db.scalars(q)]


@router.post("/rh/crm/tags", status_code=201)
def criar_tag(payload: TagIn, db: Session = Depends(get_db)) -> dict:
    nome = (payload.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(Tag).where(Tag.nome == nome)):
        raise HTTPException(status_code=409, detail="tag_duplicada")
    t = Tag(nome=nome[:60], cor=(payload.cor or None),
            ativo=True if payload.ativo is None else payload.ativo)
    db.add(t)
    db.commit()
    return crm.dump_tag(t)


# ---------- Anotações e tags de UMA pessoa ----------

@router.get("/rh/crm/pessoa")
def memoria_da_pessoa(talento_id: uuid.UUID | None = None,
                      candidato_id: uuid.UUID | None = None,
                      db: Session = Depends(get_db)) -> dict:
    """Anotações + tags da pessoa, juntando talento e candidato quando há
    vínculo (a memória feita no talento segue para o candidato)."""
    _escopo_ou_422(talento_id, candidato_id)
    escopo = crm.escopo_pessoa(db, talento_id=talento_id, candidato_id=candidato_id)
    return {
        "anotacoes": [crm.dump_anotacao(a) for a in crm.anotacoes_da_pessoa(db, escopo)],
        "tags": [crm.dump_tag(t) for t in crm.tags_da_pessoa(db, escopo)],
    }


@router.post("/rh/crm/anotacoes", status_code=201)
def criar_anotacao(payload: AnotacaoIn, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    _escopo_ou_422(payload.talento_id, payload.candidato_id)
    texto = (payload.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="texto_obrigatorio")
    a = Anotacao(talento_id=payload.talento_id, candidato_id=payload.candidato_id,
                 texto=texto, autor_id=rh.id, autor_nome=rh.nome or rh.email)
    db.add(a)
    db.commit()
    registrar(db, "crm_anotacao_criada", ator="rh", ator_detalhe=rh.email,
              candidato_id=payload.candidato_id, detalhe={"anotacao": str(a.id)})
    return crm.dump_anotacao(a)


@router.post("/rh/crm/anotacoes/{anotacao_id}/anexo")
async def anexar(anotacao_id: uuid.UUID, arquivo: UploadFile,
                 db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    a = db.get(Anotacao, anotacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="anotacao_nao_encontrada")
    ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower() if "." in (arquivo.filename or "") else ""
    if ext not in ANEXO_EXTS:
        raise HTTPException(status_code=422, detail="formato_nao_suportado")
    try:
        dados = await arquivo.read()
        if len(dados) > ANEXO_MAX_BYTES:
            raise HTTPException(status_code=413, detail="arquivo_grande")
        # substitui anexo anterior se houver
        if a.anexo_key:
            try:
                storage.remover(a.anexo_key)
            except Exception:
                pass
        key = f"crm/anotacoes/{a.id}/anexo.{ext}"
        ct = ANEXO_CT.get(ext, arquivo.content_type or "application/octet-stream")
        storage.salvar(key, dados, ct)
        a.anexo_key, a.anexo_nome, a.anexo_tipo = key, (arquivo.filename or f"anexo.{ext}")[:200], ct
        db.commit()
    finally:
        await arquivo.close()   # Starlette faz spool em disco > ~1MB
    return crm.dump_anotacao(a)


@router.get("/rh/crm/anotacoes/{anotacao_id}/anexo")
def baixar_anexo(anotacao_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    a = db.get(Anotacao, anotacao_id)
    if a is None or not a.anexo_key:
        raise HTTPException(status_code=404, detail="anexo_nao_encontrado")
    dados = storage.ler(a.anexo_key)
    return Response(content=dados, media_type=a.anexo_tipo or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{a.anexo_nome or "anexo"}"'})


@router.delete("/rh/crm/anotacoes/{anotacao_id}", status_code=204)
def excluir_anotacao(anotacao_id: uuid.UUID, db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> Response:
    a = db.get(Anotacao, anotacao_id)
    if a is None:
        raise HTTPException(status_code=404, detail="anotacao_nao_encontrada")
    if a.anexo_key:
        try:
            storage.remover(a.anexo_key)
        except Exception:
            pass
    db.delete(a)
    db.commit()
    registrar(db, "crm_anotacao_excluida", ator="rh", ator_detalhe=rh.email,
              candidato_id=a.candidato_id, detalhe={"anotacao": str(anotacao_id)})
    return Response(status_code=204)


@router.post("/rh/crm/pessoa/tags", status_code=201)
def marcar_tag(payload: MarcarTagIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    _escopo_ou_422(payload.talento_id, payload.candidato_id)
    if db.get(Tag, payload.tag_id) is None:
        raise HTTPException(status_code=404, detail="tag_nao_encontrada")
    # idempotente: se já marcada naquele lado, não duplica
    existe = db.scalar(select(PessoaTag).where(
        PessoaTag.tag_id == payload.tag_id,
        PessoaTag.talento_id == payload.talento_id,
        PessoaTag.candidato_id == payload.candidato_id))
    if existe is None:
        db.add(PessoaTag(tag_id=payload.tag_id, talento_id=payload.talento_id,
                         candidato_id=payload.candidato_id, aplicado_por=rh.email))
        db.commit()
    return {"ok": True}


@router.delete("/rh/crm/pessoa/tags", status_code=204)
def desmarcar_tag(tag_id: uuid.UUID, talento_id: uuid.UUID | None = None,
                  candidato_id: uuid.UUID | None = None,
                  db: Session = Depends(get_db)) -> Response:
    _escopo_ou_422(talento_id, candidato_id)
    escopo = crm.escopo_pessoa(db, talento_id=talento_id, candidato_id=candidato_id)
    # remove o vínculo de qualquer lado da pessoa (talento e/ou candidato)
    q = select(PessoaTag).where(PessoaTag.tag_id == tag_id).where(
        crm._predicado(PessoaTag, escopo))
    for pt in db.scalars(q):
        db.delete(pt)
    db.commit()
    return Response(status_code=204)


# ---------- Paramétrica de tag por ÚLTIMO (não capturar os literais acima) ----------

@router.patch("/rh/crm/tags/{tag_id}")
def editar_tag(tag_id: uuid.UUID, payload: TagIn, db: Session = Depends(get_db)) -> dict:
    t = db.get(Tag, tag_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tag_nao_encontrada")
    nome = (payload.nome or "").strip()
    if nome:
        outra = db.scalar(select(Tag).where(Tag.nome == nome, Tag.id != tag_id))
        if outra:
            raise HTTPException(status_code=409, detail="tag_duplicada")
        t.nome = nome[:60]
    if payload.cor is not None:
        t.cor = payload.cor or None
    if payload.ativo is not None:
        t.ativo = payload.ativo
    db.commit()
    return crm.dump_tag(t)


@router.delete("/rh/crm/tags/{tag_id}", status_code=204)
def excluir_tag(tag_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    t = db.get(Tag, tag_id)
    if t is None:
        raise HTTPException(status_code=404, detail="tag_nao_encontrada")
    db.delete(t)   # cascade remove os vínculos PessoaTag
    db.commit()
    return Response(status_code=204)
