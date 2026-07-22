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
    # Nome obrigatório; sem e-mail, o RH copia o link e manda pelo WhatsApp.
    # O posto é escolhido no convite (obrigatório no painel): com base nele e no
    # regime, os documentos específicos do kit já nascem certos.
    nome_completo: str
    email: EmailStr | None = None
    celular_whatsapp: str | None = None
    posto_id: uuid.UUID | None = None
    # Jornada obrigatória já no convite (feedback 2026-07-21): o Tirvu recusa
    # admissão sem jornada, e exigir aqui evita descobrir a pendência lá na
    # frente. O seletor do front oferece as jornadas do posto primeiro.
    jornada_id: uuid.UUID | None = None
    regime: str = "efetivo"
    cargo_funcao: str | None = None
    # Testes marcados pelo RH ao gerar o link: o candidato responde ANTES de
    # seguir para o cadastro; o resultado é restrito ao RH.
    fazer_disc: bool = False
    fazer_situacional: bool = False

    @field_validator("nome_completo", "email", "celular_whatsapp", "cargo_funcao",
                     mode="before")
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
    Com o posto e o regime escolhidos aqui, os documentos específicos do kit
    (INFRAERO / Informativo do Intermitente) já nascem exigidos."""
    from app.api.postos import gerar_docs_do_posto_e_regime
    from app.models.candidato import Jornada, PostoServico

    dados = payload.model_dump()
    posto_id = dados.pop("posto_id", None)
    jornada_id = dados.pop("jornada_id", None)
    regime = (dados.pop("regime", None) or "efetivo").strip().lower()
    cargo = dados.pop("cargo_funcao", None)
    fazer_disc = bool(dados.pop("fazer_disc", False))
    fazer_situacional = bool(dados.pop("fazer_situacional", False))
    if posto_id is not None and db.get(PostoServico, posto_id) is None:
        raise HTTPException(status_code=404, detail="posto_nao_encontrado")
    # Jornada é obrigatória no convite (feedback 2026-07-21) e precisa existir.
    if jornada_id is None:
        raise HTTPException(status_code=422, detail="jornada_obrigatoria")
    if db.get(Jornada, jornada_id) is None:
        raise HTTPException(status_code=404, detail="jornada_nao_encontrada")
    candidato = Candidato(**dados, posto_servico_id=posto_id, jornada_id=jornada_id,
                          regime=regime if regime in ("efetivo", "intermitente") else "efetivo",
                          cargo_funcao=cargo)
    db.add(candidato)
    db.flush()
    docs_novos = gerar_docs_do_posto_e_regime(db, candidato)
    # testes marcados no convite (respondidos antes do cadastro)
    from app.models.teste import TesteCandidato, TipoTeste
    if fazer_disc:
        db.add(TesteCandidato(candidato_id=candidato.id, tipo=TipoTeste.disc))
    if fazer_situacional:
        db.add(TesteCandidato(candidato_id=candidato.id, tipo=TipoTeste.situacional))
    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "convite_criado", ator="rh", ator_detalhe=_rh.email, candidato_id=candidato.id,
              detalhe={"posto": str(posto_id), "regime": candidato.regime,
                       "docs_kit": [d.value for d in docs_novos]})
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
