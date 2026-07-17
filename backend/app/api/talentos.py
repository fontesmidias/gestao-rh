"""Banco de Talentos: cadastro público de interessados + triagem e conversão
em candidato pelo RH."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.talento import StatusTalento, Talento
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import email_convite, enviar_email
from app.services.magic_link import emitir_link

router = APIRouter(tags=["talentos"])

# Cargos sugeridos no formulário público (o interessado também pode digitar).
CARGOS_SUGERIDOS = [
    "Auxiliar de Limpeza", "Auxiliar de Serviços Gerais", "Copeiro(a)",
    "Recepcionista", "Porteiro(a)", "Vigia", "Jardineiro(a)", "Motorista",
    "Auxiliar Administrativo", "Encarregado(a)", "Outro",
]


# ---------- Público (sem autenticação) ----------


class TalentoIn(BaseModel):
    nome: str
    email: EmailStr | None = None
    telefone: str | None = None
    cargo_interesse: str | None = None
    cidade: str | None = None
    escolaridade: str | None = None
    resumo: str | None = None
    origem: str | None = None
    # Honeypot anti-spam: campo escondido no formulário; humano deixa vazio.
    # (Não pode começar com "_": o pydantic trata como atributo privado.)
    website: str | None = None

    @field_validator("nome", "telefone", "cargo_interesse", "cidade",
                     "escolaridade", "resumo", "origem", mode="before")
    @classmethod
    def _apara(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v or None


@router.get("/talentos/opcoes")
def opcoes_publicas() -> dict:
    return {"cargos": CARGOS_SUGERIDOS}


@router.post("/talentos", status_code=201)
def cadastrar(payload: TalentoIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Cadastro público no Banco de Talentos. Sem autenticação — protegido por
    honeypot e limite de tamanho; o RH tria depois."""
    dados = payload.model_dump()
    if dados.pop("website", None):
        # Bot preencheu o campo escondido: responde 201 sem gravar (não dá pistas).
        return {"ok": True}
    if not (dados.get("nome") or "").strip():
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    if dados.get("resumo") and len(dados["resumo"]) > 4000:
        dados["resumo"] = dados["resumo"][:4000]
    talento = Talento(**dados)
    db.add(talento)
    registrar(db, "talento_cadastrado", ator="publico",
              detalhe={"cargo": talento.cargo_interesse, "cidade": talento.cidade})
    db.commit()
    return {"ok": True}


# ---------- RH (protegido) ----------


def _dump(t: Talento) -> dict:
    return {
        "id": t.id, "nome": t.nome, "email": t.email, "telefone": t.telefone,
        "cargo_interesse": t.cargo_interesse, "cidade": t.cidade,
        "escolaridade": t.escolaridade, "resumo": t.resumo, "origem": t.origem,
        "status": t.status.value, "candidato_id": t.candidato_id, "criado_em": t.criado_em,
    }


@router.get("/rh/talentos", dependencies=[Depends(requer_rh)])
def listar(status: str | None = None, busca: str | None = None,
           cargo: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    consulta = select(Talento).order_by(Talento.criado_em.desc())
    if status:
        consulta = consulta.where(Talento.status == status)
    if cargo:
        consulta = consulta.where(Talento.cargo_interesse.ilike(f"%{cargo}%"))
    if busca:
        termo = f"%{busca.lower()}%"
        consulta = consulta.where(or_(
            Talento.nome.ilike(termo), Talento.email.ilike(termo),
            Talento.cidade.ilike(termo), Talento.resumo.ilike(termo)))
    return [_dump(t) for t in db.scalars(consulta).all()]


class StatusIn(BaseModel):
    status: StatusTalento


@router.put("/rh/talentos/{talento_id}/status", dependencies=[Depends(requer_rh)])
def mudar_status(talento_id: uuid.UUID, payload: StatusIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if t.status == StatusTalento.convertido:
        raise HTTPException(status_code=409, detail="talento_ja_convertido")
    t.status = payload.status
    registrar(db, "talento_status_alterado", ator="rh", ator_detalhe=rh.email,
              detalhe={"talento": t.nome, "status": t.status.value})
    db.commit()
    return _dump(t)


@router.post("/rh/talentos/{talento_id}/converter", dependencies=[Depends(requer_rh)])
def converter(talento_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Converte o talento em candidato: cria o cadastro migrando nome/contato,
    emite o link mágico da admissão e (se houver e-mail) envia o convite."""
    t = db.get(Talento, talento_id)
    if t is None:
        raise HTTPException(status_code=404, detail="talento_nao_encontrado")
    if t.status == StatusTalento.convertido and t.candidato_id:
        raise HTTPException(status_code=409, detail="talento_ja_convertido")

    candidato = Candidato(nome_completo=t.nome, email=t.email,
                          celular_whatsapp=t.telefone,
                          cargo_funcao=t.cargo_interesse)
    db.add(candidato)
    db.flush()
    link = emitir_link(db, candidato, base_url_publica(request))
    t.status = StatusTalento.convertido
    t.candidato_id = candidato.id
    registrar(db, "talento_convertido", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id, detalhe={"talento": t.nome})
    db.commit()

    enviado = False
    if candidato.email:
        assunto, texto, html = email_convite(candidato.nome_completo, link)
        enviado = enviar_email(candidato.email, assunto, texto, html)
    return {"candidato_id": candidato.id, "link_magico": link, "email_enviado": enviado}
