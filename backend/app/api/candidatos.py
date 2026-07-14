import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.services.magic_link import emitir_link, resolver_token

router = APIRouter(tags=["candidatos"])


class NovoCandidato(BaseModel):
    nome_completo: str
    email: EmailStr
    celular_whatsapp: str


class CandidatoOut(BaseModel):
    id: uuid.UUID
    nome_completo: str
    email: EmailStr
    celular_whatsapp: str
    status: StatusCandidato

    model_config = {"from_attributes": True}


class ConviteOut(BaseModel):
    candidato: CandidatoOut
    link_magico: str


# --- RH (TODO: proteger com autenticação do RH no módulo seguinte) ---


@router.post("/rh/candidatos", response_model=ConviteOut, status_code=201)
def criar_candidato(payload: NovoCandidato, db: Session = Depends(get_db)) -> ConviteOut:
    """Cadastra o candidato aprovado e emite o link mágico (envio por e-mail no módulo SMTP)."""
    candidato = Candidato(**payload.model_dump())
    db.add(candidato)
    db.flush()
    link = emitir_link(db, candidato)
    db.commit()
    return ConviteOut(candidato=CandidatoOut.model_validate(candidato), link_magico=link)


# --- Candidato (acesso via token do link mágico) ---


@router.get("/c/{token}", response_model=CandidatoOut)
def sessao_candidato(token: str, db: Session = Depends(get_db)) -> CandidatoOut:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    db.commit()
    return CandidatoOut.model_validate(candidato)
