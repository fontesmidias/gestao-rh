"""Match de Vagas × Banco de Talentos (v1.99): o RH cadastra a vaga e o
sistema ranqueia os talentos aderentes, lendo também o currículo com IA.

Base legal LGPD: o termo do Banco de Talentos (Talentos.jsx) já autoriza
"tratar os dados para fins de recrutamento" — cobre a triagem por IA, que é
uso primário da finalidade, não secundário (verificado no roundtable de
2026-07-27). Groq é o operador (decisão consciente do Bruno, mesmo sem
cláusula de retenção zero) — a proteção que resta é MINIMIZAÇÃO (CPF/RG/
telefone/e-mail/CEP removidos antes do envio, ver curriculo_texto.minimizar)
e AUDITORIA SEM CONTEÚDO (quem pediu, qual vaga, quantos CVs — nunca o
texto).

O currículo é ENTRADA HOSTIL — ver services/anti_prompt_injection.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.talento import Talento
from app.models.usuario_rh import UsuarioRH
from app.models.vaga import Vaga
from app.services.auditoria import registrar
from app.services.match_vagas import ranquear_talentos

router = APIRouter(tags=["vagas"], dependencies=[Depends(requer_rh)])


def _dump_vaga(v: Vaga) -> dict:
    return {
        "id": v.id, "titulo": v.titulo, "descricao": v.descricao,
        "requisitos_obrigatorios": v.requisitos_obrigatorios,
        "requisitos_desejaveis": v.requisitos_desejaveis,
        "cargo": v.cargo, "regiao": v.regiao, "regime": v.regime,
        "salario_min": v.salario_min, "salario_max": v.salario_max,
        "ativa": v.ativa, "criado_em": v.criado_em,
    }


class VagaIn(BaseModel):
    titulo: str
    descricao: str = ""
    requisitos_obrigatorios: str | None = None
    requisitos_desejaveis: str | None = None
    cargo: str | None = None
    regiao: str | None = None
    regime: str | None = None
    salario_min: str | None = None
    salario_max: str | None = None
    ativa: bool | None = None


@router.get("/rh/vagas")
def listar_vagas(incluir_inativas: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    q = select(Vaga).order_by(Vaga.criado_em.desc())
    if not incluir_inativas:
        q = q.where(Vaga.ativa.is_(True))
    return [_dump_vaga(v) for v in db.scalars(q)]


@router.post("/rh/vagas", status_code=201)
def criar_vaga(payload: VagaIn, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    titulo = payload.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="titulo_obrigatorio")
    v = Vaga(titulo=titulo[:160], descricao=payload.descricao.strip(),
             requisitos_obrigatorios=payload.requisitos_obrigatorios,
             requisitos_desejaveis=payload.requisitos_desejaveis,
             cargo=payload.cargo, regiao=payload.regiao, regime=payload.regime,
             salario_min=payload.salario_min, salario_max=payload.salario_max,
             ativa=True if payload.ativa is None else payload.ativa)
    db.add(v)
    db.flush()
    registrar(db, "vaga_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"vaga": str(v.id), "titulo": titulo})
    db.commit()
    return _dump_vaga(v)


@router.patch("/rh/vagas/{vaga_id}")
def editar_vaga(vaga_id: uuid.UUID, payload: VagaIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    v = db.get(Vaga, vaga_id)
    if v is None:
        raise HTTPException(status_code=404, detail="vaga_nao_encontrada")
    titulo = payload.titulo.strip()
    if not titulo:
        raise HTTPException(status_code=422, detail="titulo_obrigatorio")
    v.titulo = titulo[:160]
    v.descricao = payload.descricao.strip()
    v.requisitos_obrigatorios = payload.requisitos_obrigatorios
    v.requisitos_desejaveis = payload.requisitos_desejaveis
    v.cargo = payload.cargo
    v.regiao = payload.regiao
    v.regime = payload.regime
    v.salario_min = payload.salario_min
    v.salario_max = payload.salario_max
    if payload.ativa is not None:
        v.ativa = payload.ativa
    registrar(db, "vaga_editada", ator="rh", ator_detalhe=rh.email, detalhe={"vaga": str(v.id)})
    db.commit()
    return _dump_vaga(v)


@router.delete("/rh/vagas/{vaga_id}", status_code=204)
def excluir_vaga(vaga_id: uuid.UUID, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    v = db.get(Vaga, vaga_id)
    if v is None:
        raise HTTPException(status_code=404, detail="vaga_nao_encontrada")
    db.delete(v)
    registrar(db, "vaga_excluida", ator="rh", ator_detalhe=rh.email, detalhe={"vaga": str(vaga_id)})
    db.commit()


class RanquearIn(BaseModel):
    talento_ids: list[uuid.UUID] = []  # vazio = todos os talentos não-arquivados


@router.post("/rh/vagas/{vaga_id}/ranquear")
def ranquear(vaga_id: uuid.UUID, payload: RanquearIn, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Ranqueia os talentos por aderência à vaga: filtro estruturado local
    primeiro (barato), depois leitura do currículo por IA (quando houver
    currículo e chave configurada). A IA NUNCA decide sozinha — devolve nota
    + justificativa, o RH convoca. Auditoria registra QUANTOS currículos
    foram processados, NUNCA o conteúdo."""
    vaga = db.get(Vaga, vaga_id)
    if vaga is None:
        raise HTTPException(status_code=404, detail="vaga_nao_encontrada")

    if payload.talento_ids:
        talentos = [t for tid in payload.talento_ids if (t := db.get(Talento, tid)) is not None]
    else:
        talentos = list(db.scalars(
            select(Talento).where(Talento.status != "arquivado")))

    resultado = ranquear_talentos(vaga, talentos)

    registrar(db, "vaga_ranqueada", ator="rh", ator_detalhe=rh.email,
              detalhe={"vaga": str(vaga_id), "total_talentos": len(talentos),
                       "curriculos_analisados": resultado["curriculos_analisados"],
                       "curriculos_suspeitos": resultado["curriculos_suspeitos"]})
    db.commit()
    return resultado
