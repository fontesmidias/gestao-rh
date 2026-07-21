"""Provas por cargo: CRUD (RH monta as provas), aplicação pública por link avulso
(a pessoa responde sem login, como a testagem /t/) e correção mista (objetivas
automáticas + discursivas do RH).

Segurança: o GABARITO das objetivas nunca aparece em rota pública — só no CRUD do
RH e na correção. O participante não vê a própria nota (é seleção)."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, ip_do_cliente
from app.core.db import get_db
from app.models.prova import (AplicacaoProva, LinkProva, ProvaCargo, QuestaoProva)
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.lixeira import mandar_para_lixeira
from app.services.limite import exigir

router = APIRouter(tags=["provas"])

TIPOS_QUESTAO = {"objetiva", "discursiva"}


# ===========================================================================
# Helpers de serialização
# ===========================================================================


def _dump_questao_rh(q: QuestaoProva) -> dict:
    """Versão do RH — INCLUI o gabarito (para editar/corrigir)."""
    return {"id": q.id, "ordem": q.ordem, "enunciado": q.enunciado, "tipo": q.tipo,
            "opcoes": q.opcoes or [], "gabarito": q.gabarito, "peso": q.peso}


def _questao_publica(q: QuestaoProva) -> dict:
    """Versão do PARTICIPANTE — sem gabarito; opções só {id, texto}."""
    return {"id": str(q.id), "ordem": q.ordem, "enunciado": q.enunciado, "tipo": q.tipo,
            "opcoes": [{"id": o.get("id"), "texto": o.get("texto")} for o in (q.opcoes or [])]}


def _questoes(db: Session, prova_id: uuid.UUID) -> list[QuestaoProva]:
    return db.scalars(select(QuestaoProva)
                      .where(QuestaoProva.prova_id == prova_id)
                      .order_by(QuestaoProva.ordem, QuestaoProva.criado_em)).all()


def _dump_prova(db: Session, p: ProvaCargo, com_questoes: bool = False) -> dict:
    qs = _questoes(db, p.id)
    d = {"id": p.id, "titulo": p.titulo, "cargo": p.cargo, "descricao": p.descricao,
         "tempo_segundos": p.tempo_segundos, "ativa": p.ativa,
         "qtd_questoes": len(qs),
         "qtd_objetivas": sum(1 for q in qs if q.tipo == "objetiva"),
         "qtd_discursivas": sum(1 for q in qs if q.tipo == "discursiva"),
         "criado_em": p.criado_em}
    if com_questoes:
        d["questoes"] = [_dump_questao_rh(q) for q in qs]
    return d


# ===========================================================================
# CRUD das provas (RH)
# ===========================================================================


@router.get("/rh/provas", dependencies=[Depends(requer_rh)])
def listar_provas(db: Session = Depends(get_db)) -> list[dict]:
    provas = db.scalars(select(ProvaCargo).order_by(ProvaCargo.criado_em.desc())).all()
    return [_dump_prova(db, p) for p in provas]


class ProvaIn(BaseModel):
    titulo: str
    cargo: str | None = None
    descricao: str | None = None
    tempo_segundos: int | None = None
    ativa: bool | None = None


@router.post("/rh/provas", status_code=201, dependencies=[Depends(requer_rh)])
def criar_prova(payload: ProvaIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    if not (payload.titulo or "").strip():
        raise HTTPException(status_code=422, detail="titulo_obrigatorio")
    p = ProvaCargo(titulo=payload.titulo.strip()[:200],
                   cargo=(payload.cargo or "").strip()[:120] or None,
                   descricao=(payload.descricao or "").strip() or None,
                   tempo_segundos=max(60, min(14400, payload.tempo_segundos or 1800)),
                   ativa=True if payload.ativa is None else payload.ativa,
                   criado_por=rh.email)
    db.add(p)
    registrar(db, "prova_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"titulo": p.titulo, "cargo": p.cargo})
    db.commit()
    return _dump_prova(db, p, com_questoes=True)


@router.get("/rh/provas/{prova_id}", dependencies=[Depends(requer_rh)])
def detalhe_prova(prova_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    return _dump_prova(db, p, com_questoes=True)


@router.put("/rh/provas/{prova_id}", dependencies=[Depends(requer_rh)])
def editar_prova(prova_id: uuid.UUID, payload: ProvaIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    if payload.titulo and payload.titulo.strip():
        p.titulo = payload.titulo.strip()[:200]
    if payload.cargo is not None:
        p.cargo = payload.cargo.strip()[:120] or None
    if payload.descricao is not None:
        p.descricao = payload.descricao.strip() or None
    if payload.tempo_segundos is not None:
        p.tempo_segundos = max(60, min(14400, payload.tempo_segundos))
    if payload.ativa is not None:
        p.ativa = payload.ativa
    registrar(db, "prova_editada", ator="rh", ator_detalhe=rh.email, detalhe={"titulo": p.titulo})
    db.commit()
    return _dump_prova(db, p, com_questoes=True)


@router.delete("/rh/provas/{prova_id}", status_code=204, dependencies=[Depends(requer_rh)])
def excluir_prova(prova_id: uuid.UUID, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> None:
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    mandar_para_lixeira(db, p, "prova_cargo", p.titulo, rh.email)
    registrar(db, "prova_excluida", ator="rh", ator_detalhe=rh.email, detalhe={"titulo": p.titulo})
    db.delete(p)  # cascade remove as questões
    db.commit()


# ===========================================================================
# Questões de uma prova (RH)
# ===========================================================================


class QuestaoIn(BaseModel):
    enunciado: str
    tipo: str                        # objetiva | discursiva
    opcoes: list[dict] | None = None  # [{id, texto}] (objetiva)
    gabarito: str | None = None       # id da opção certa (objetiva)
    peso: int | None = None
    ordem: int | None = None


def _validar_questao(payload: QuestaoIn) -> None:
    if payload.tipo not in TIPOS_QUESTAO:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    if not (payload.enunciado or "").strip():
        raise HTTPException(status_code=422, detail="enunciado_obrigatorio")
    if payload.tipo == "objetiva":
        opcoes = payload.opcoes or []
        if len(opcoes) < 2:
            raise HTTPException(status_code=422, detail="objetiva_precisa_2_opcoes")
        ids = [str(o.get("id")) for o in opcoes]
        if payload.gabarito is None or str(payload.gabarito) not in ids:
            raise HTTPException(status_code=422, detail="gabarito_invalido")


@router.post("/rh/provas/{prova_id}/questoes", status_code=201,
             dependencies=[Depends(requer_rh)])
def criar_questao(prova_id: uuid.UUID, payload: QuestaoIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    _validar_questao(payload)
    ordem = payload.ordem if payload.ordem is not None else len(_questoes(db, prova_id))
    q = QuestaoProva(
        prova_id=prova_id, ordem=ordem, enunciado=payload.enunciado.strip(),
        tipo=payload.tipo,
        opcoes=([{"id": str(o.get("id")), "texto": str(o.get("texto", "")).strip()}
                 for o in payload.opcoes] if payload.tipo == "objetiva" else None),
        gabarito=(str(payload.gabarito) if payload.tipo == "objetiva" else None),
        peso=max(1, payload.peso or 1))
    db.add(q)
    registrar(db, "prova_questao_criada", ator="rh", ator_detalhe=rh.email,
              detalhe={"prova": p.titulo, "tipo": q.tipo})
    db.commit()
    return _dump_questao_rh(q)


@router.put("/rh/provas/{prova_id}/questoes/{questao_id}", dependencies=[Depends(requer_rh)])
def editar_questao(prova_id: uuid.UUID, questao_id: uuid.UUID, payload: QuestaoIn,
                   db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    q = db.get(QuestaoProva, questao_id)
    if q is None or q.prova_id != prova_id:
        raise HTTPException(status_code=404, detail="questao_nao_encontrada")
    _validar_questao(payload)
    q.enunciado = payload.enunciado.strip()
    q.tipo = payload.tipo
    q.opcoes = ([{"id": str(o.get("id")), "texto": str(o.get("texto", "")).strip()}
                 for o in payload.opcoes] if payload.tipo == "objetiva" else None)
    q.gabarito = str(payload.gabarito) if payload.tipo == "objetiva" else None
    q.peso = max(1, payload.peso or 1)
    if payload.ordem is not None:
        q.ordem = payload.ordem
    registrar(db, "prova_questao_editada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return _dump_questao_rh(q)


@router.delete("/rh/provas/{prova_id}/questoes/{questao_id}", status_code=204,
               dependencies=[Depends(requer_rh)])
def excluir_questao(prova_id: uuid.UUID, questao_id: uuid.UUID,
                    db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> None:
    q = db.get(QuestaoProva, questao_id)
    if q is None or q.prova_id != prova_id:
        raise HTTPException(status_code=404, detail="questao_nao_encontrada")
    db.delete(q)
    registrar(db, "prova_questao_excluida", ator="rh", ator_detalhe=rh.email)
    db.commit()


# ===========================================================================
# Criar link de aplicação (RH)
# ===========================================================================


class LinkIn(BaseModel):
    nome: str | None = None


@router.post("/rh/provas/{prova_id}/link", status_code=201, dependencies=[Depends(requer_rh)])
def criar_link(prova_id: uuid.UUID, payload: LinkIn, request: Request,
               db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    if not _questoes(db, prova_id):
        raise HTTPException(status_code=422, detail="prova_sem_questoes")
    link = LinkProva(prova_id=prova_id, token=secrets.token_urlsafe(16),
                     nome=(payload.nome or p.titulo)[:120], criado_por=rh.email)
    db.add(link)
    registrar(db, "prova_link_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"prova": p.titulo})
    db.commit()
    return {"token": link.token, "url": f"{base_url_publica(request)}/p/{link.token}"}


# ===========================================================================
# Aplicação pública (sem login) — a pessoa responde a prova por um link
# ===========================================================================


def _link(token: str, db: Session, exigir_ativo: bool = True) -> LinkProva:
    link = db.scalar(select(LinkProva).where(LinkProva.token == token))
    if link is None:
        raise HTTPException(status_code=404, detail="link_invalido")
    if exigir_ativo and not link.ativo:
        raise HTTPException(status_code=403, detail="link_desativado")
    return link


def _aplicacao(link: LinkProva, aid: uuid.UUID, db: Session) -> AplicacaoProva:
    a = db.get(AplicacaoProva, aid)
    if a is None or a.link_id != link.id:
        raise HTTPException(status_code=404, detail="aplicacao_nao_encontrada")
    return a


def _expira_se_estourou(db: Session, a: AplicacaoProva) -> None:
    if (a.status == "em_andamento" and a.prazo_ate
            and a.prazo_ate < datetime.now(timezone.utc)):
        _corrigir_objetivas(db, a)
        a.status = "expirado"
        a.concluido_em = datetime.now(timezone.utc)
        db.commit()


def _corrigir_objetivas(db: Session, a: AplicacaoProva) -> None:
    """Nota das objetivas (0-100): soma dos pesos das acertadas / soma dos pesos
    das objetivas. Gabarito lido do banco — nunca do cliente."""
    questoes = {str(q.id): q for q in _questoes(db, a.prova_id)}
    respostas = {str(r.get("questao_id")): r for r in (a.respostas or [])}
    peso_total = peso_ok = 0
    for qid, q in questoes.items():
        if q.tipo != "objetiva":
            continue
        peso_total += q.peso
        r = respostas.get(qid)
        if r and str(r.get("escolha")) == str(q.gabarito):
            peso_ok += q.peso
    a.nota_objetivas = round(100.0 * peso_ok / peso_total, 1) if peso_total else None


@router.get("/p/{token}")
def info_prova(token: str, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db, exigir_ativo=False)
    p = db.get(ProvaCargo, link.prova_id)
    return {"nome": link.nome, "ativo": link.ativo,
            "titulo": p.titulo if p else link.nome,
            "descricao": p.descricao if p else None}


class ParticiparIn(BaseModel):
    nome: str


@router.post("/p/{token}/participar", status_code=201)
def participar_prova(token: str, payload: ParticiparIn, request: Request,
                     db: Session = Depends(get_db)) -> dict:
    nome = payload.nome.strip()
    if len(nome) < 3:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    exigir(f"prova:ip:{ip_do_cliente(request) or '?'}", maximo=20, janela_s=3600)
    link = _link(token, db)
    a = AplicacaoProva(link_id=link.id, prova_id=link.prova_id, nome=nome[:200])
    db.add(a)
    registrar(db, "prova_participante_criado", ator="participante",
              detalhe={"prova": link.nome, "nome": nome[:200]})
    db.commit()
    return {"aplicacao_id": a.id}


@router.post("/p/{token}/a/{aid}/iniciar")
def iniciar_prova(token: str, aid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    a = _aplicacao(link, aid, db)
    _expira_se_estourou(db, a)
    if a.status == "em_andamento":
        return _dump_aplicacao(db, a)  # retomada
    if a.status != "pendente":
        raise HTTPException(status_code=409, detail="prova_ja_realizada")
    p = db.get(ProvaCargo, a.prova_id)
    a.status = "em_andamento"
    a.iniciado_em = datetime.now(timezone.utc)
    a.prazo_ate = a.iniciado_em + timedelta(seconds=p.tempo_segundos if p else 1800)
    db.commit()
    return _dump_aplicacao(db, a)


def _dump_aplicacao(db: Session, a: AplicacaoProva) -> dict:
    restante = None
    if a.status == "em_andamento" and a.prazo_ate:
        restante = max(0, int((a.prazo_ate - datetime.now(timezone.utc)).total_seconds()))
    total = len(_questoes(db, a.prova_id))
    return {"status": a.status, "segundos_restantes": restante,
            "respondidas": len(a.respostas or []), "total": total}


@router.get("/p/{token}/a/{aid}/questoes")
def questoes_prova(token: str, aid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    a = _aplicacao(link, aid, db)
    _expira_se_estourou(db, a)
    if a.status != "em_andamento":
        raise HTTPException(status_code=409, detail="prova_nao_iniciada")
    qs = [_questao_publica(q) for q in _questoes(db, a.prova_id)]  # SEM gabarito
    return {"questoes": qs, **_dump_aplicacao(db, a)}


class RespostaIn(BaseModel):
    questao_id: str
    escolha: str | None = None   # objetiva
    texto: str | None = None     # discursiva


@router.post("/p/{token}/a/{aid}/responder")
def responder_prova(token: str, aid: uuid.UUID, payload: RespostaIn,
                    db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    a = _aplicacao(link, aid, db)
    _expira_se_estourou(db, a)
    if a.status != "em_andamento":
        raise HTTPException(status_code=409, detail="prova_nao_iniciada")
    q = db.get(QuestaoProva, uuid.UUID(payload.questao_id)) if _uuid_ok(payload.questao_id) else None
    if q is None or q.prova_id != a.prova_id:
        raise HTTPException(status_code=422, detail="questao_invalida")
    if q.tipo == "objetiva":
        if not payload.escolha:
            raise HTTPException(status_code=422, detail="escolha_obrigatoria")
        nova = {"questao_id": payload.questao_id, "escolha": str(payload.escolha)[:40]}
    else:
        nova = {"questao_id": payload.questao_id, "texto": (payload.texto or "").strip()[:5000]}
    respostas = [r for r in (a.respostas or []) if str(r.get("questao_id")) != payload.questao_id]
    respostas.append(nova)
    a.respostas = respostas
    db.commit()
    return {"respondidas": len(respostas)}


@router.post("/p/{token}/a/{aid}/concluir")
def concluir_prova(token: str, aid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    a = _aplicacao(link, aid, db)
    if a.status == "expirado":
        return {"status": a.status}
    if a.status != "em_andamento":
        raise HTTPException(status_code=409, detail="prova_nao_iniciada")
    _corrigir_objetivas(db, a)
    a.status = "concluido"
    a.concluido_em = datetime.now(timezone.utc)
    db.commit()
    # o participante NÃO recebe a nota (é seleção — restrita ao RH)
    return {"status": a.status}


class EventosIn(BaseModel):
    eventos: list[dict]


_MAX_EVENTOS = 800


@router.post("/p/{token}/a/{aid}/eventos", status_code=204)
def eventos_prova(token: str, aid: uuid.UUID, payload: EventosIn,
                  db: Session = Depends(get_db)) -> None:
    link = _link(token, db)
    a = _aplicacao(link, aid, db)
    if a.status not in ("em_andamento", "concluido", "expirado"):
        return
    atuais = list(a.eventos or [])
    for ev in payload.eventos[: _MAX_EVENTOS - len(atuais)]:
        if isinstance(ev, dict) and ev.get("e"):
            atuais.append({"t": round(float(ev.get("t") or 0), 1), "e": str(ev["e"])[:40],
                           **({"d": str(ev["d"])[:120]} if ev.get("d") else {})})
    a.eventos = atuais
    db.commit()


def _uuid_ok(v: str) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except (ValueError, TypeError):
        return False
