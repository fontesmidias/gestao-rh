"""Postos de serviço: cadastro pelo RH e vínculo do candidato ao posto,
gerando os documentos adicionais para assinatura (ex.: INFRAERO)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.assinatura import FICHAS_BASE, Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, PostoServico
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.magic_link import emitir_link

router = APIRouter(tags=["postos-rh"], dependencies=[Depends(requer_rh)])

DOCS_INFRAERO = (DocumentoAssinavel.oficio_cartao_cidadao,
                 DocumentoAssinavel.informacoes_trabalhador)


# ---------- CRUD de postos ----------


class PostoIn(BaseModel):
    nome: str
    contrato_ref: str | None = None


@router.get("/rh/postos")
def listar_postos(db: Session = Depends(get_db)) -> list[dict]:
    postos = db.scalars(select(PostoServico).order_by(PostoServico.nome)).all()
    return [{"id": p.id, "nome": p.nome, "contrato_ref": p.contrato_ref} for p in postos]


@router.post("/rh/postos", status_code=201)
def criar_posto(payload: PostoIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if db.scalar(select(PostoServico).where(PostoServico.nome == nome)):
        raise HTTPException(status_code=409, detail="posto_ja_existe")
    posto = PostoServico(nome=nome,
                         contrato_ref=(payload.contrato_ref or "").strip() or None)
    db.add(posto)
    registrar(db, "posto_criado", ator="rh", ator_detalhe=rh.email, detalhe={"nome": nome})
    db.commit()
    return {"id": posto.id, "nome": posto.nome, "contrato_ref": posto.contrato_ref}


@router.put("/rh/postos/{posto_id}")
def editar_posto(posto_id: uuid.UUID, payload: PostoIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    posto = db.get(PostoServico, posto_id)
    if posto is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    if payload.nome.strip():
        posto.nome = payload.nome.strip()
    posto.contrato_ref = (payload.contrato_ref or "").strip() or None
    registrar(db, "posto_editado", ator="rh", ator_detalhe=rh.email,
              detalhe={"nome": posto.nome})
    db.commit()
    return {"id": posto.id, "nome": posto.nome, "contrato_ref": posto.contrato_ref}


# ---------- Vínculo do candidato + geração dos documentos ----------


class PostoCandidatoIn(BaseModel):
    posto_id: uuid.UUID | None = None  # None = remover o posto
    cargo_funcao: str | None = None


@router.put("/rh/candidatos/{candidato_id}/posto")
def definir_posto(candidato_id: uuid.UUID, payload: PostoCandidatoIn, request: Request,
                  db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Vincula o candidato ao posto. Se o posto exige documentos adicionais
    (INFRAERO), eles entram na fila de assinatura e o candidato é avisado por
    e-mail com um link novo — o mesmo código único assina tudo."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")

    docs_novos: list[DocumentoAssinavel] = []
    if payload.posto_id is None:
        candidato.posto_servico_id = None
        candidato.cargo_funcao = (payload.cargo_funcao or "").strip() or None
    else:
        posto = db.get(PostoServico, payload.posto_id)
        if posto is None:
            raise HTTPException(status_code=404, detail="posto_nao_encontrado")
        candidato.posto_servico_id = posto.id
        candidato.cargo_funcao = (payload.cargo_funcao or "").strip() or None
        if posto.exige_docs_infraero:
            existentes = {
                a.documento for a in db.scalars(
                    select(Assinatura).where(Assinatura.candidato_id == candidato.id,
                                             Assinatura.invalidada_em.is_(None))
                ).all()
            }
            for doc in DOCS_INFRAERO:
                if doc not in existentes:
                    db.add(Assinatura(candidato_id=candidato.id, documento=doc))
                    docs_novos.append(doc)

    registrar(db, "posto_definido", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"posto": str(candidato.posto_servico_id),
                       "cargo": candidato.cargo_funcao,
                       "docs_gerados": [d.value for d in docs_novos]})
    db.commit()

    email_enviado = False
    if docs_novos:
        from app.api.assinaturas import NOMES_DOC
        link = emitir_link(db, candidato, base_url_publica(request))
        db.commit()
        docs_html = "".join(f"<li>{NOMES_DOC[d]}</li>" for d in docs_novos)
        email_enviado = enviar_email(
            candidato.email,
            "Green House — novos documentos aguardam a sua assinatura",
            f"Prezado(a) {candidato.nome_completo},\n\n"
            "O seu posto de serviço exige a assinatura dos documentos abaixo:\n"
            + "\n".join(f"  - {NOMES_DOC[d]}" for d in docs_novos)
            + f"\n\nAcesse: {link}\n\n"
            "Assine HOJE: sem essas assinaturas, sua alocação no posto não pode ser "
            "concluída.\n\nAtenciosamente,\nRH — Green House\n",
            html_moderno(
                "Novos documentos para assinar",
                [
                    f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                    "O seu posto de serviço exige a assinatura dos documentos abaixo:"
                    f"<ul style='margin:8px 0 0 18px;color:#3a4152'>{docs_html}</ul>",
                    "<strong>Assine HOJE</strong> — sem essas assinaturas, sua alocação "
                    "no posto não pode ser concluída. O processo é o mesmo: um código "
                    "chega no seu e-mail e assina tudo de uma vez.",
                ],
                botao_texto="Assinar os documentos",
                botao_url=link,
            ),
        )
    return {
        "posto_servico_id": candidato.posto_servico_id,
        "cargo_funcao": candidato.cargo_funcao,
        "docs_gerados": [d.value for d in docs_novos],
        "email_enviado": email_enviado,
    }
