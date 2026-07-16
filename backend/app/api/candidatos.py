import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import email_convite, enviar_email
from app.services.magic_link import emitir_link, resolver_token

router = APIRouter(tags=["candidatos"])


from pydantic import field_validator


class NovoCandidato(BaseModel):
    # Só o nome é obrigatório: sem e-mail, o RH copia o link e manda pelo
    # WhatsApp; o candidato completa e-mail e celular na própria ficha.
    nome_completo: str
    email: EmailStr | None = None
    celular_whatsapp: str | None = None

    @field_validator("nome_completo", "email", "celular_whatsapp", mode="before")
    @classmethod
    def _apara_espacos(cls, v):
        # E-mails colados do WhatsApp costumam vir com espaço no fim;
        # campo deixado em branco no formulário chega como "".
        if isinstance(v, str):
            v = v.strip()
        return v or None


class CandidatoOut(BaseModel):
    id: uuid.UUID
    nome_completo: str
    email: EmailStr | None = None
    celular_whatsapp: str | None = None
    status: StatusCandidato

    model_config = {"from_attributes": True}


class ConviteOut(BaseModel):
    candidato: CandidatoOut
    link_magico: str
    email_enviado: bool


# --- RH (protegido) ---


@router.post("/rh/candidatos", response_model=ConviteOut, status_code=201)
def criar_candidato(
    payload: NovoCandidato,
    request: Request,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> ConviteOut:
    """Cadastra o candidato aprovado, emite o link mágico e envia o convite por e-mail.
    O link também volta na resposta: se o SMTP falhar, o RH envia manualmente (WhatsApp)."""
    candidato = Candidato(**payload.model_dump())
    db.add(candidato)
    db.flush()
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "convite_criado", ator="rh", ator_detalhe=_rh.email, candidato_id=candidato.id)
    db.commit()
    enviado = False
    if candidato.email:
        assunto, texto, html = email_convite(candidato.nome_completo, link)
        enviado = enviar_email(candidato.email, assunto, texto, html)
    return ConviteOut(
        candidato=CandidatoOut.model_validate(candidato), link_magico=link, email_enviado=enviado
    )


@router.post("/rh/candidatos/{candidato_id}/reenviar-link", response_model=ConviteOut)
def reenviar_link(
    candidato_id: uuid.UUID,
    request: Request,
    enviar_email_convite: bool = True,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> ConviteOut:
    """Emite um novo link mágico (o anterior continua válido até expirar).
    Com enviar_email_convite=false, só gera e devolve o link — para o RH copiar
    e mandar por WhatsApp, sem duplicar e-mail para o candidato."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "link_reenviado" if enviar_email_convite else "link_copiado",
              ator="rh", ator_detalhe=_rh.email, candidato_id=candidato.id)
    db.commit()
    enviado = False
    if enviar_email_convite and candidato.email:
        assunto, texto, html = email_convite(candidato.nome_completo, link)
        enviado = enviar_email(candidato.email, assunto, texto, html)
    return ConviteOut(
        candidato=CandidatoOut.model_validate(candidato), link_magico=link, email_enviado=enviado
    )


class ContatoIn(BaseModel):
    email: EmailStr | None = None
    celular_whatsapp: str | None = None

    @field_validator("email", "celular_whatsapp", mode="before")
    @classmethod
    def _apara(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v or None


@router.put("/rh/candidatos/{candidato_id}/contato", response_model=CandidatoOut)
def editar_contato(
    candidato_id: uuid.UUID,
    payload: ContatoIn,
    db: Session = Depends(get_db),
    _rh: UsuarioRH = Depends(requer_rh),
) -> CandidatoOut:
    """O RH corrige e-mail/celular do candidato (caso real: cadastro sem
    e-mail → fichas e código de assinatura não chegavam). O antes e o depois
    ficam na auditoria — evidência para qualquer contestação de assinatura."""
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    antes = {"email": candidato.email, "celular_whatsapp": candidato.celular_whatsapp}
    dados = payload.model_dump(exclude_unset=True)
    for campo, valor in dados.items():
        setattr(candidato, campo, valor)
    registrar(db, "contato_alterado", ator="rh", ator_detalhe=_rh.email,
              candidato_id=candidato.id,
              detalhe={"antes": antes,
                       "depois": {"email": candidato.email,
                                  "celular_whatsapp": candidato.celular_whatsapp}})
    db.commit()
    return CandidatoOut.model_validate(candidato)


# --- Candidato (acesso via token do link mágico) ---


@router.get("/c/{token}", response_model=CandidatoOut)
def sessao_candidato(token: str, db: Session = Depends(get_db)) -> CandidatoOut:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    db.commit()
    return CandidatoOut.model_validate(candidato)
