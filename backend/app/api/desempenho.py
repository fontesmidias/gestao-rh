"""Gestão de Desempenho — painel do RH e da liderança (Onda C).

Primeira fatia: **Fatos Observados**. Rodam sozinhos, sem depender do
formulário — e é assim de propósito: quando a avaliação nascer, ela já abre com
os fatos do período ao lado, e o líder REVISA o que registrou em vez de
escrever do zero com a memória vazia.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato, PostoServico
from app.models.desempenho import Avaliacao, FatoObservado, TipoFato
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.desempenho import formulario

router = APIRouter(tags=["desempenho-rh"], dependencies=[Depends(requer_rh)])

EXT_ACEITAS = {"pdf", "jpg", "jpeg", "png", "heic", "webp", "mp4", "mov", "3gp",
               "doc", "docx"}
# Vídeo é o formato que o Bruno pediu, e é o que enche disco: um plantão inteiro
# gravado tem centenas de MB. 25 MB cobre um clipe curto de celular.
TAMANHO_MAX = 25 * 1024 * 1024
DURACAO_AVISO = "Prefira clipes curtos: o limite é 25 MB por anexo."


def _dump_fato(db: Session, f: FatoObservado, para_colaborador: bool = False) -> dict:
    col = db.get(Candidato, f.candidato_id)
    dados = {
        "id": str(f.id),
        "candidato_id": str(f.candidato_id),
        "colaborador": col.nome_completo if col else "—",
        "tipo": f.tipo.value,
        "descricao": f.descricao,
        "impacto": f.impacto,
        "ocorrido_em": f.ocorrido_em.isoformat() if f.ocorrido_em else None,
        "tem_anexo": bool(f.anexo_key),
        "anexo_nome": f.anexo_nome,
        "visivel_em": f.visivel_em.isoformat() if f.visivel_em else None,
        "criado_em": f.criado_em.isoformat() if f.criado_em else None,
        "usado_em_avaliacao": f.avaliacao_id is not None,
    }
    if not para_colaborador:
        # o autor aparece para o RH/liderança; para o avaliado, ver `_dump_para_colaborador`
        dados["autor"] = f.autor
    return dados


class FatoIn(BaseModel):
    candidato_id: uuid.UUID
    tipo: str = "positivo"
    descricao: str
    impacto: str | None = None
    ocorrido_em: str | None = None      # aaaa-mm-dd; vazio = hoje
    visivel_em: str | None = None       # atraso opcional até a conversa


def _data_de(txt: str | None) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((txt or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


@router.get("/rh/desempenho/fatos")
def listar_fatos(candidato_id: uuid.UUID | None = None, tipo: str | None = None,
                 desde: str | None = None, ate: str | None = None,
                 db: Session = Depends(get_db)) -> dict:
    """Fatos registrados. Filtro pesado SERVER-SIDE; o DashPlanilha refina em
    memória por cima (padrão da casa — isto cresce sem parar)."""
    consulta = select(FatoObservado)
    if candidato_id:
        consulta = consulta.where(FatoObservado.candidato_id == candidato_id)
    if tipo:
        consulta = consulta.where(FatoObservado.tipo.in_(
            [t.strip() for t in tipo.split(",") if t.strip()]))
    d1, d2 = _data_de(desde), _data_de(ate)
    if d1:
        consulta = consulta.where(FatoObservado.ocorrido_em >= d1)
    if d2:
        consulta = consulta.where(FatoObservado.ocorrido_em <= d2)
    fatos = db.scalars(consulta.order_by(FatoObservado.ocorrido_em.desc())).all()

    contagem = dict(db.execute(
        select(FatoObservado.tipo, func.count())
        .group_by(FatoObservado.tipo)).all())
    return {
        "fatos": [_dump_fato(db, f) for f in fatos],
        "metricas": {t.value: contagem.get(t, 0) for t in TipoFato},
        "limite_anexo_mb": TAMANHO_MAX // (1024 * 1024),
    }


@router.post("/rh/desempenho/fatos", status_code=201)
def criar_fato(payload: FatoIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Registra um fato. A descrição é obrigatória — sem ela não há fato, só
    rótulo, que é exatamente o que a cartilha (pág. 3) manda evitar."""
    col = db.get(Candidato, payload.candidato_id)
    if col is None:
        raise HTTPException(status_code=404, detail="colaborador_nao_encontrado")
    if not (payload.descricao or "").strip():
        raise HTTPException(status_code=422, detail="descricao_obrigatoria")
    if payload.tipo not in {t.value for t in TipoFato}:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    ocorrido = _data_de(payload.ocorrido_em) or date.today()
    if ocorrido > date.today():
        raise HTTPException(status_code=422, detail="data_futura")

    f = FatoObservado(
        candidato_id=col.id, autor=rh.email, tipo=TipoFato(payload.tipo),
        descricao=payload.descricao.strip(),
        impacto=(payload.impacto or "").strip() or None,
        ocorrido_em=ocorrido, visivel_em=_data_de(payload.visivel_em))
    db.add(f)
    registrar(db, "fato_observado_registrado", ator="rh", ator_detalhe=rh.email,
              candidato_id=col.id, detalhe={"tipo": f.tipo.value})
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.put("/rh/desempenho/fatos/{fato_id}")
def editar_fato(fato_id: uuid.UUID, payload: FatoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Só o AUTOR corrige o próprio registro, e só enquanto não foi usado numa
    avaliação — depois disso é peça de um documento fechado."""
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    if f.avaliacao_id is not None:
        raise HTTPException(status_code=409, detail="fato_ja_usado")
    if not (payload.descricao or "").strip():
        raise HTTPException(status_code=422, detail="descricao_obrigatoria")
    f.descricao = payload.descricao.strip()
    f.impacto = (payload.impacto or "").strip() or None
    if payload.tipo in {t.value for t in TipoFato}:
        f.tipo = TipoFato(payload.tipo)
    nova_data = _data_de(payload.ocorrido_em)
    if nova_data:
        if nova_data > date.today():
            raise HTTPException(status_code=422, detail="data_futura")
        f.ocorrido_em = nova_data
    registrar(db, "fato_observado_editado", ator="rh", ator_detalhe=rh.email,
              candidato_id=f.candidato_id)
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.delete("/rh/desempenho/fatos/{fato_id}", status_code=204)
def excluir_fato(fato_id: uuid.UUID, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    if f.avaliacao_id is not None:
        raise HTTPException(status_code=409, detail="fato_ja_usado")
    if f.anexo_key:
        try:
            storage.remover(f.anexo_key)
        except Exception:
            pass
    registrar(db, "fato_observado_excluido", ator="rh", ator_detalhe=rh.email,
              candidato_id=f.candidato_id, detalhe={"descricao": f.descricao[:120]})
    db.delete(f)
    db.commit()


@router.post("/rh/desempenho/fatos/{fato_id}/anexo")
async def subir_anexo(fato_id: uuid.UUID, arquivo: UploadFile,
                      db: Session = Depends(get_db),
                      rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Anexo do fato (foto, vídeo curto, documento)."""
    f = db.get(FatoObservado, fato_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fato_nao_encontrado")
    if f.autor != rh.email:
        raise HTTPException(status_code=403, detail="somente_o_autor")
    try:
        conteudo = await arquivo.read()
        if not conteudo:
            raise HTTPException(status_code=422, detail="arquivo_vazio")
        if len(conteudo) > TAMANHO_MAX:
            raise HTTPException(status_code=422, detail="arquivo_grande")
        ext = (arquivo.filename or "").rsplit(".", 1)[-1].lower()[:5]
        if ext not in EXT_ACEITAS:
            raise HTTPException(status_code=422, detail="formato_nao_aceito")
    finally:
        # Starlette faz spool em disco acima de ~1MB — sem o close, o temp file
        # ficaria no container (regra da casa).
        await arquivo.close()

    if f.anexo_key:
        try:
            storage.remover(f.anexo_key)
        except Exception:
            pass
    key = f"desempenho/fatos/{f.id}/anexo.{ext}"
    storage.salvar(key, conteudo, arquivo.content_type or "application/octet-stream")
    f.anexo_key = key
    f.anexo_nome = (arquivo.filename or "")[:200]
    f.anexo_tipo = arquivo.content_type
    f.anexo_tamanho = len(conteudo)
    db.commit()
    db.refresh(f)
    return _dump_fato(db, f)


@router.get("/rh/desempenho/fatos/{fato_id}/anexo")
def baixar_anexo(fato_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    f = db.get(FatoObservado, fato_id)
    if f is None or not f.anexo_key:
        raise HTTPException(status_code=404, detail="anexo_nao_encontrado")
    try:
        dados = storage.ler(f.anexo_key)
    except Exception:
        raise HTTPException(status_code=404, detail="anexo_indisponivel")
    return Response(content=dados,
                    media_type=f.anexo_tipo or "application/octet-stream",
                    headers={"Content-Disposition":
                             f'inline; filename="{f.anexo_nome or "anexo"}"'})


@router.get("/rh/desempenho/formulario")
def ver_formulario() -> dict:
    """Escalas, indicadores, competências e recomendações da cartilha — o front
    desenha o formulário a partir daqui, sem duplicar os textos."""
    return formulario()


@router.get("/rh/desempenho/colaboradores")
def listar_colaboradores(db: Session = Depends(get_db)) -> dict:
    """Quem pode receber fato/avaliação: colaboradores ativos."""
    linhas = []
    for c in db.scalars(select(Candidato).where(Candidato.situacao == "ativo")
                        .order_by(Candidato.nome_completo)):
        posto = db.get(PostoServico, c.posto_servico_id) if c.posto_servico_id else None
        linhas.append({"id": str(c.id), "nome": c.nome_completo,
                       "cargo": c.cargo_funcao, "posto": posto.nome if posto else None})
    return {"colaboradores": linhas}
