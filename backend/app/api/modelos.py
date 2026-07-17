"""CRUD de modelos de documento criados pelo RH (layout timbrado + variáveis)
e geração do PDF preenchido para um colaborador."""

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.modelo_documento import EscopoModelo, ModeloDocumento
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.fichas import (VARIAVEIS_MODELO, gerar_documento_modelo)

router = APIRouter(tags=["modelos-documento"], dependencies=[Depends(requer_rh)])


class ModeloIn(BaseModel):
    titulo: str
    corpo: str
    escopo: EscopoModelo = EscopoModelo.avulso
    cargo_alvo: str | None = None
    posto_alvo_id: uuid.UUID | None = None
    candidato_alvo_id: uuid.UUID | None = None


def _dump(m: ModeloDocumento) -> dict:
    return {
        "id": m.id, "titulo": m.titulo, "corpo": m.corpo, "escopo": m.escopo.value,
        "cargo_alvo": m.cargo_alvo, "posto_alvo_id": m.posto_alvo_id,
        "candidato_alvo_id": m.candidato_alvo_id, "criado_em": m.criado_em,
        "atualizado_em": m.atualizado_em,
    }


def _aplicar(m: ModeloDocumento, payload: ModeloIn) -> None:
    m.titulo = payload.titulo.strip()
    m.corpo = payload.corpo
    m.escopo = payload.escopo
    # Só o alvo do escopo escolhido é guardado; os demais zeram.
    m.cargo_alvo = payload.cargo_alvo.strip() if (
        payload.escopo == EscopoModelo.cargo and payload.cargo_alvo) else None
    m.posto_alvo_id = payload.posto_alvo_id if payload.escopo == EscopoModelo.posto else None
    m.candidato_alvo_id = (payload.candidato_alvo_id
                           if payload.escopo == EscopoModelo.colaborador else None)


@router.get("/rh/modelos-documento")
def listar(db: Session = Depends(get_db)) -> dict:
    modelos = db.scalars(select(ModeloDocumento).order_by(ModeloDocumento.titulo)).all()
    return {"modelos": [_dump(m) for m in modelos],
            "variaveis": VARIAVEIS_MODELO}


@router.post("/rh/modelos-documento", status_code=201)
def criar(payload: ModeloIn, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not payload.titulo.strip() or not payload.corpo.strip():
        raise HTTPException(status_code=422, detail="titulo_e_corpo_obrigatorios")
    m = ModeloDocumento()
    _aplicar(m, payload)
    db.add(m)
    registrar(db, "modelo_documento_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo, "escopo": m.escopo.value})
    db.commit()
    return _dump(m)


@router.put("/rh/modelos-documento/{modelo_id}")
def editar(modelo_id: uuid.UUID, payload: ModeloIn, db: Session = Depends(get_db),
           rh: UsuarioRH = Depends(requer_rh)) -> dict:
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    _aplicar(m, payload)
    registrar(db, "modelo_documento_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo})
    db.commit()
    return _dump(m)


@router.delete("/rh/modelos-documento/{modelo_id}", status_code=204)
def excluir(modelo_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> None:
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    registrar(db, "modelo_documento_excluido", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": m.titulo})
    db.delete(m)
    db.commit()


@router.get("/rh/modelos-documento/{modelo_id}/previa")
def previa(modelo_id: uuid.UUID, db: Session = Depends(get_db)) -> StreamingResponse:
    """Prévia sem colaborador: as variáveis aparecem como {{...}}."""
    m = db.get(ModeloDocumento, modelo_id)
    if m is None:
        raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
    pdf = gerar_documento_modelo(db, m.titulo, m.corpo, None)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf")


@router.get("/rh/candidatos/{candidato_id}/modelos-aplicaveis")
def aplicaveis(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    """Modelos que valem para este colaborador: avulsos + do seu cargo + do seu
    posto + os anexados diretamente a ele."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    condicoes = [ModeloDocumento.escopo == EscopoModelo.avulso,
                 ModeloDocumento.candidato_alvo_id == candidato.id]
    if candidato.cargo_funcao:
        condicoes.append((ModeloDocumento.escopo == EscopoModelo.cargo)
                         & (ModeloDocumento.cargo_alvo == candidato.cargo_funcao))
    if candidato.posto_servico_id:
        condicoes.append((ModeloDocumento.escopo == EscopoModelo.posto)
                         & (ModeloDocumento.posto_alvo_id == candidato.posto_servico_id))
    modelos = db.scalars(
        select(ModeloDocumento).where(or_(*condicoes)).order_by(ModeloDocumento.titulo)
    ).all()
    return [{"id": m.id, "titulo": m.titulo, "escopo": m.escopo.value} for m in modelos]


@router.get("/rh/candidatos/{candidato_id}/modelos/{modelo_id}/gerar")
def gerar(candidato_id: uuid.UUID, modelo_id: uuid.UUID, db: Session = Depends(get_db),
          rh: UsuarioRH = Depends(requer_rh)) -> StreamingResponse:
    """Gera o PDF do modelo com as variáveis preenchidas para o colaborador."""
    candidato = db.get(Candidato, candidato_id)
    m = db.get(ModeloDocumento, modelo_id)
    if candidato is None or m is None:
        raise HTTPException(status_code=404, detail="nao_encontrado")
    pdf = gerar_documento_modelo(db, m.titulo, m.corpo, candidato)
    registrar(db, "modelo_documento_gerado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id, detalhe={"titulo": m.titulo})
    db.commit()
    nome = "".join(c for c in m.titulo if c.isalnum() or c in " -_").strip()[:60] or "documento"
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}.pdf"'})
