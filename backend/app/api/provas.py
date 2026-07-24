"""Provas por cargo: CRUD (RH monta as provas), aplicação pública por link avulso
(a pessoa responde sem login, como a testagem /t/) e correção mista (objetivas
automáticas + discursivas do RH).

Segurança: o GABARITO das objetivas nunca aparece em rota pública — só no CRUD do
RH e na correção. O participante não vê a própria nota (é seleção)."""

import random
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
from app.models.prova import (SENIORIDADES, AplicacaoProva, ItemBanco, LinkProva,
                              ProvaCargo, QuestaoProva)
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
            "opcoes": q.opcoes or [], "gabarito": q.gabarito, "peso": q.peso,
            "explicacao": q.explicacao}


def _questao_publica(q: QuestaoProva) -> dict:
    """Versão do PARTICIPANTE — sem gabarito; opções só {id, texto}."""
    return {"id": str(q.id), "ordem": q.ordem, "enunciado": q.enunciado, "tipo": q.tipo,
            "opcoes": [{"id": o.get("id"), "texto": o.get("texto")} for o in (q.opcoes or [])]}


def _questoes(db: Session, prova_id: uuid.UUID) -> list[QuestaoProva]:
    return db.scalars(select(QuestaoProva)
                      .where(QuestaoProva.prova_id == prova_id)
                      .order_by(QuestaoProva.ordem, QuestaoProva.criado_em)).all()


def _publicas_ordenadas(questoes: list[QuestaoProva], embaralhar: bool,
                        seed: int | None) -> list[dict]:
    """Versões públicas das questões, na ordem que o PARTICIPANTE vê.

    Sem embaralhar: ordem fixa (a de _questoes). Embaralhando: permuta as
    questões E as opções de cada uma de forma DETERMINÍSTICA pela seed — mesma
    seed → mesma ordem sempre (recarregar não reembaralha). A correção casa por
    id da opção (não por posição), então embaralhar a EXIBIÇÃO nunca altera a
    nota. Cada questão usa uma sub-seed distinta (seed + índice) para as opções
    não embaralharem todas igual."""
    pubs = [_questao_publica(q) for q in questoes]
    if not embaralhar or seed is None:
        return pubs
    random.Random(seed).shuffle(pubs)   # permuta a ordem das questões
    for i, pub in enumerate(pubs):
        if pub.get("opcoes"):
            random.Random(seed + i + 1).shuffle(pub["opcoes"])  # e das opções
    return pubs


def _dump_prova(db: Session, p: ProvaCargo, com_questoes: bool = False) -> dict:
    qs = _questoes(db, p.id)
    d = {"id": p.id, "titulo": p.titulo, "cargo": p.cargo, "descricao": p.descricao,
         "tempo_segundos": p.tempo_segundos, "ativa": p.ativa,
         "embaralhar": p.embaralhar, "mostrar_explicacao": p.mostrar_explicacao,
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
    embaralhar: bool | None = None
    mostrar_explicacao: bool | None = None


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
                   embaralhar=bool(payload.embaralhar),
                   mostrar_explicacao=bool(payload.mostrar_explicacao),
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
    if payload.embaralhar is not None:
        p.embaralhar = payload.embaralhar
    if payload.mostrar_explicacao is not None:
        p.mostrar_explicacao = payload.mostrar_explicacao
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


@router.post("/rh/provas/{prova_id}/duplicar", status_code=201,
             dependencies=[Depends(requer_rh)])
def duplicar_prova(prova_id: uuid.UUID, db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Clona a prova inteira (config + todas as questões, com gabarito e
    explicação). A cópia nasce com título "(cópia)" e as MESMAS questões, mas
    sem links/aplicações (é um novo modelo)."""
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")
    nova = ProvaCargo(
        titulo=f"{p.titulo} (cópia)"[:200], cargo=p.cargo, descricao=p.descricao,
        tempo_segundos=p.tempo_segundos, ativa=p.ativa, embaralhar=p.embaralhar,
        mostrar_explicacao=p.mostrar_explicacao, criado_por=rh.email)
    db.add(nova)
    db.flush()
    for q in _questoes(db, prova_id):
        db.add(QuestaoProva(
            prova_id=nova.id, ordem=q.ordem, enunciado=q.enunciado, tipo=q.tipo,
            opcoes=q.opcoes, gabarito=q.gabarito, explicacao=q.explicacao, peso=q.peso))
    registrar(db, "prova_duplicada", ator="rh", ator_detalhe=rh.email,
              detalhe={"origem": p.titulo, "nova": nova.titulo})
    db.commit()
    return _dump_prova(db, nova, com_questoes=True)


# ===========================================================================
# Questões de uma prova (RH)
# ===========================================================================


class QuestaoIn(BaseModel):
    enunciado: str
    tipo: str                        # objetiva | discursiva
    opcoes: list[dict] | None = None  # [{id, texto}] (objetiva)
    gabarito: str | None = None       # id da opção certa (objetiva)
    explicacao: str | None = None     # por que a resposta é correta (opcional)
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
        explicacao=(payload.explicacao or "").strip() or None,
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
    q.explicacao = (payload.explicacao or "").strip() or None
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


@router.post("/rh/provas/{prova_id}/questoes/{questao_id}/duplicar", status_code=201,
             dependencies=[Depends(requer_rh)])
def duplicar_questao(prova_id: uuid.UUID, questao_id: uuid.UUID,
                     db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Clona uma questão na MESMA prova (enunciado, opções, gabarito, explicação,
    peso). A cópia entra ao final da ordem."""
    q = db.get(QuestaoProva, questao_id)
    if q is None or q.prova_id != prova_id:
        raise HTTPException(status_code=404, detail="questao_nao_encontrada")
    nova = QuestaoProva(
        prova_id=prova_id, ordem=len(_questoes(db, prova_id)),
        enunciado=q.enunciado, tipo=q.tipo, opcoes=q.opcoes, gabarito=q.gabarito,
        explicacao=q.explicacao, peso=q.peso)
    db.add(nova)
    registrar(db, "prova_questao_duplicada", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return _dump_questao_rh(nova)


# ===========================================================================
# Banco de itens (Fase 2): questões reutilizáveis por cargo/senioridade/tags.
# ADITIVO — não toca as provas existentes. Montar prova COPIA o item (snapshot).
# ===========================================================================


def _dump_item(it: ItemBanco) -> dict:
    return {"id": it.id, "enunciado": it.enunciado, "tipo": it.tipo,
            "opcoes": it.opcoes or [], "gabarito": it.gabarito,
            "explicacao": it.explicacao, "peso": it.peso, "cargo": it.cargo,
            "senioridade": it.senioridade, "tags": it.tags or [],
            "criado_em": it.criado_em}


class ItemIn(BaseModel):
    enunciado: str
    tipo: str
    opcoes: list[dict] | None = None
    gabarito: str | None = None
    explicacao: str | None = None
    peso: int | None = None
    cargo: str | None = None
    senioridade: str | None = None
    tags: list[str] | None = None


def _validar_item(payload: ItemIn) -> None:
    if payload.tipo not in TIPOS_QUESTAO:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    if not (payload.enunciado or "").strip():
        raise HTTPException(status_code=422, detail="enunciado_obrigatorio")
    if payload.senioridade and payload.senioridade not in SENIORIDADES:
        raise HTTPException(status_code=422, detail="senioridade_invalida")
    if payload.tipo == "objetiva":
        opcoes = payload.opcoes or []
        if len(opcoes) < 2:
            raise HTTPException(status_code=422, detail="objetiva_precisa_2_opcoes")
        ids = [str(o.get("id")) for o in opcoes]
        if payload.gabarito is None or str(payload.gabarito) not in ids:
            raise HTTPException(status_code=422, detail="gabarito_invalido")


def _campos_item(payload: ItemIn) -> dict:
    return {
        "enunciado": payload.enunciado.strip(), "tipo": payload.tipo,
        "opcoes": ([{"id": str(o.get("id")), "texto": str(o.get("texto", "")).strip()}
                    for o in payload.opcoes] if payload.tipo == "objetiva" else None),
        "gabarito": str(payload.gabarito) if payload.tipo == "objetiva" else None,
        "explicacao": (payload.explicacao or "").strip() or None,
        "peso": max(1, payload.peso or 1),
        "cargo": (payload.cargo or "").strip()[:120] or None,
        "senioridade": payload.senioridade or "qualquer",
        "tags": [t.strip() for t in (payload.tags or []) if t.strip()][:20] or None,
    }


@router.get("/rh/banco-itens", dependencies=[Depends(requer_rh)])
def listar_itens(cargo: str | None = None, senioridade: str | None = None,
                 tag: str | None = None, tipo: str | None = None,
                 db: Session = Depends(get_db)) -> dict:
    """Lista os itens do banco, filtrando por cargo/senioridade/tag/tipo. Também
    devolve os cargos e tags existentes (p/ alimentar os seletores do front)."""
    q = select(ItemBanco).order_by(ItemBanco.criado_em.desc())
    if cargo:
        q = q.where(ItemBanco.cargo.ilike(f"%{cargo}%"))
    if senioridade and senioridade != "qualquer":
        # 'qualquer' do item serve a todos; então o filtro casa o nível OU genérico
        q = q.where(ItemBanco.senioridade.in_([senioridade, "qualquer"]))
    if tipo in TIPOS_QUESTAO:
        q = q.where(ItemBanco.tipo == tipo)
    itens = list(db.scalars(q))
    if tag:
        alvo = tag.strip().lower()
        itens = [it for it in itens if any(alvo in (t or "").lower() for t in (it.tags or []))]
    cargos = sorted({it.cargo for it in db.scalars(select(ItemBanco)) if it.cargo})
    tags = sorted({t for it in db.scalars(select(ItemBanco)) for t in (it.tags or [])})
    return {"itens": [_dump_item(it) for it in itens],
            "cargos": cargos, "tags": tags, "senioridades": list(SENIORIDADES)}


@router.post("/rh/banco-itens", status_code=201, dependencies=[Depends(requer_rh)])
def criar_item(payload: ItemIn, db: Session = Depends(get_db),
               rh: UsuarioRH = Depends(requer_rh)) -> dict:
    _validar_item(payload)
    it = ItemBanco(**_campos_item(payload), criado_por=rh.email)
    db.add(it)
    registrar(db, "banco_item_criado", ator="rh", ator_detalhe=rh.email,
              detalhe={"cargo": it.cargo, "senioridade": it.senioridade})
    db.commit()
    return _dump_item(it)


@router.put("/rh/banco-itens/{item_id}", dependencies=[Depends(requer_rh)])
def editar_item(item_id: uuid.UUID, payload: ItemIn, db: Session = Depends(get_db),
                rh: UsuarioRH = Depends(requer_rh)) -> dict:
    it = db.get(ItemBanco, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item_nao_encontrado")
    _validar_item(payload)
    for k, v in _campos_item(payload).items():
        setattr(it, k, v)
    registrar(db, "banco_item_editado", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return _dump_item(it)


@router.delete("/rh/banco-itens/{item_id}", status_code=204, dependencies=[Depends(requer_rh)])
def excluir_item(item_id: uuid.UUID, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> None:
    it = db.get(ItemBanco, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item_nao_encontrado")
    mandar_para_lixeira(db, it, "item_banco", it.enunciado[:80], rh.email)
    registrar(db, "banco_item_excluido", ator="rh", ator_detalhe=rh.email)
    db.delete(it)
    db.commit()


class PromoverIn(BaseModel):
    cargo: str | None = None
    senioridade: str | None = None
    tags: list[str] | None = None


@router.post("/rh/provas/{prova_id}/questoes/{questao_id}/promover", status_code=201,
             dependencies=[Depends(requer_rh)])
def promover_para_banco(prova_id: uuid.UUID, questao_id: uuid.UUID, payload: PromoverIn,
                        db: Session = Depends(get_db), rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Reaproveita uma questão de uma prova existente: COPIA para o banco de
    itens (a questão original continua na prova). Cargo/senioridade/tags podem
    ser informados na promoção; o cargo cai no da prova se não vier."""
    q = db.get(QuestaoProva, questao_id)
    if q is None or q.prova_id != prova_id:
        raise HTTPException(status_code=404, detail="questao_nao_encontrada")
    if payload.senioridade and payload.senioridade not in SENIORIDADES:
        raise HTTPException(status_code=422, detail="senioridade_invalida")
    prova = db.get(ProvaCargo, prova_id)
    it = ItemBanco(
        enunciado=q.enunciado, tipo=q.tipo, opcoes=q.opcoes, gabarito=q.gabarito,
        explicacao=q.explicacao, peso=q.peso,
        cargo=(payload.cargo or (prova.cargo if prova else None)),
        senioridade=payload.senioridade or "qualquer",
        tags=[t.strip() for t in (payload.tags or []) if t.strip()][:20] or None,
        criado_por=rh.email)
    db.add(it)
    registrar(db, "banco_item_promovido", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return _dump_item(it)


class MontarIn(BaseModel):
    item_ids: list[uuid.UUID] | None = None   # escolha manual
    # ou sorteio automático por filtro:
    quantidade: int | None = None
    cargo: str | None = None
    senioridade: str | None = None
    tag: str | None = None


@router.post("/rh/provas/{prova_id}/adicionar-do-banco", status_code=201,
             dependencies=[Depends(requer_rh)])
def adicionar_do_banco(prova_id: uuid.UUID, payload: MontarIn, db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Adiciona itens do banco a uma prova, COPIANDO cada item para uma
    QuestaoProva (snapshot — editar o item depois não muda a prova). Dois modos:
    - MANUAL: `item_ids` escolhidos a dedo.
    - SORTEIO: `quantidade` + filtros (cargo/senioridade/tag) — sorteia do banco.
    Não desmonta nada existente: só ACRESCENTA questões ao final da prova."""
    p = db.get(ProvaCargo, prova_id)
    if p is None:
        raise HTTPException(status_code=404, detail="prova_nao_encontrada")

    if payload.item_ids:
        itens = [db.get(ItemBanco, i) for i in payload.item_ids]
        itens = [it for it in itens if it is not None]
    else:
        n = max(1, min(100, payload.quantidade or 0))
        if n == 0:
            raise HTTPException(status_code=422, detail="informe_itens_ou_quantidade")
        q = select(ItemBanco)
        if payload.cargo:
            q = q.where(ItemBanco.cargo.ilike(f"%{payload.cargo}%"))
        if payload.senioridade and payload.senioridade != "qualquer":
            q = q.where(ItemBanco.senioridade.in_([payload.senioridade, "qualquer"]))
        candidatos = list(db.scalars(q))
        if payload.tag:
            alvo = payload.tag.strip().lower()
            candidatos = [it for it in candidatos
                          if any(alvo in (t or "").lower() for t in (it.tags or []))]
        if not candidatos:
            raise HTTPException(status_code=422, detail="banco_sem_itens_no_filtro")
        random.shuffle(candidatos)
        itens = candidatos[:n]

    base = len(_questoes(db, prova_id))
    for i, it in enumerate(itens):
        db.add(QuestaoProva(
            prova_id=prova_id, ordem=base + i, enunciado=it.enunciado, tipo=it.tipo,
            opcoes=it.opcoes, gabarito=it.gabarito, explicacao=it.explicacao, peso=it.peso))
    registrar(db, "prova_itens_do_banco", ator="rh", ator_detalhe=rh.email,
              detalhe={"prova": p.titulo, "qtd": len(itens)})
    db.commit()
    return _dump_prova(db, p, com_questoes=True)


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
        _fechar_aplicacao(db, a)
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


def _fechar_aplicacao(db: Session, a: AplicacaoProva) -> None:
    """Fecha a aplicação (conclusão ou expiração): corrige as objetivas e, se a
    prova NÃO tem discursivas, já grava a nota_final — ela é definitiva, não há
    o que o RH corrigir. Antes a nota_final só era calculada ao corrigir
    discursivas, então prova só-objetiva concluída ficava com nota_final=null e
    aparecia "—" no dash (o RH via a prova feita mas "sem pontuação"). Com
    discursivas, mantém-se null até a correção (comportamento correto)."""
    questoes = _questoes(db, a.prova_id)
    tem_discursiva = any(q.tipo != "objetiva" for q in questoes)
    if tem_discursiva:
        _corrigir_objetivas(db, a)
    else:
        _recalcular_nota_final(db, a)  # também preenche nota_objetivas


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
    if a.seed is None:   # semente do embaralhamento, fixa a partir daqui
        a.seed = secrets.randbelow(2**31)
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
    p = db.get(ProvaCargo, a.prova_id)
    qs = _publicas_ordenadas(_questoes(db, a.prova_id),   # SEM gabarito
                             bool(p and p.embaralhar), a.seed)
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
    _fechar_aplicacao(db, a)
    a.status = "concluido"
    a.concluido_em = datetime.now(timezone.utc)
    db.commit()
    # o participante NÃO recebe a nota (é seleção — restrita ao RH). Mas se a
    # prova permitir, ele pode rever gabarito+explicação (didática).
    p = db.get(ProvaCargo, a.prova_id)
    return {"status": a.status, "tem_revisao": bool(p and p.mostrar_explicacao)}


@router.get("/p/{token}/a/{aid}/revisao")
def revisao_prova(token: str, aid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Revisão pós-prova para o PARTICIPANTE: gabarito + explicação de cada
    questão. SÓ liberada se a prova tem mostrar_explicacao E a aplicação já
    terminou. NÃO devolve nota (continua seleção — nota é só do RH). Para prova
    de seleção (flag desligada), responde 403 e nada vaza."""
    link = _link(token, db, exigir_ativo=False)
    a = _aplicacao(link, aid, db)
    if a.status not in ("concluido", "expirado"):
        raise HTTPException(status_code=409, detail="prova_nao_concluida")
    p = db.get(ProvaCargo, a.prova_id)
    if not (p and p.mostrar_explicacao):
        raise HTTPException(status_code=403, detail="revisao_indisponivel")
    escolhas = {str(r.get("questao_id")): r for r in (a.respostas or [])}
    itens = []
    for q in _questoes(db, a.prova_id):
        r = escolhas.get(str(q.id)) or {}
        item = {"enunciado": q.enunciado, "tipo": q.tipo, "explicacao": q.explicacao}
        if q.tipo == "objetiva":
            item["opcoes"] = q.opcoes or []
            item["gabarito"] = q.gabarito
            item["escolha"] = r.get("escolha")
            item["acertou"] = str(r.get("escolha")) == str(q.gabarito) if r else False
        else:
            item["resposta"] = r.get("texto") or ""
        itens.append(item)
    return {"itens": itens}


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


# ===========================================================================
# Correção e acompanhamento (RH)
# ===========================================================================


def _recalcular_nota_final(db: Session, a: AplicacaoProva) -> None:
    """Combina objetivas (auto) + discursivas (RH) ponderadas por peso, 0-100.
    Cada objetiva certa vale seu peso; cada discursiva vale (nota/100)*peso; a
    nota final é o total ganho / peso total de TODAS as questões."""
    questoes = {str(q.id): q for q in _questoes(db, a.prova_id)}
    respostas = {str(r.get("questao_id")): r for r in (a.respostas or [])}
    correcao = a.correcao_discursivas or {}
    peso_total = ganho_obj = ganho_disc = peso_disc = 0.0
    for qid, q in questoes.items():
        peso_total += q.peso
        if q.tipo == "objetiva":
            r = respostas.get(qid)
            if r and str(r.get("escolha")) == str(q.gabarito):
                ganho_obj += q.peso
        else:  # discursiva
            peso_disc += q.peso
            nota = (correcao.get(qid) or {}).get("nota")
            if nota is not None:
                ganho_disc += (float(nota) / 100.0) * q.peso
    a.nota_objetivas = round(100.0 * ganho_obj / (peso_total or 1), 1) if peso_total else None
    a.nota_discursivas = (round(100.0 * ganho_disc / peso_disc, 1) if peso_disc else None)
    a.nota_final = round(100.0 * (ganho_obj + ganho_disc) / peso_total, 1) if peso_total else None


def _dump_aplicacao_rh(db: Session, a: AplicacaoProva, com_respostas: bool = False) -> dict:
    from app.api.testes import _resumo_eventos
    p = db.get(ProvaCargo, a.prova_id)
    questoes = _questoes(db, a.prova_id)
    disc = [q for q in questoes if q.tipo == "discursiva"]
    corrigidas = len((a.correcao_discursivas or {}))
    comportamento = _resumo_eventos(a.eventos or [])
    # Sinalizador compacto de integridade para o DASH (a telemetria JÁ era
    # coletada, mas só aparecia no detalhe — feedback do Bruno). Conta os sinais
    # que sugerem "prova comprometida": saídas da tela, print, copiar/colar.
    alertas = 0
    if comportamento:
        alertas = (comportamento.get("saidas_da_tela", 0)
                   + comportamento.get("tentativas_print", 0)
                   + comportamento.get("copiar_colar", 0))
    d = {
        "id": a.id, "nome": a.nome, "prova_id": a.prova_id,
        "prova_titulo": p.titulo if p else "—", "cargo": p.cargo if p else None,
        "status": a.status, "iniciado_em": a.iniciado_em, "concluido_em": a.concluido_em,
        "nota_objetivas": a.nota_objetivas, "nota_discursivas": a.nota_discursivas,
        "nota_final": a.nota_final,
        "discursivas_total": len(disc), "discursivas_corrigidas": corrigidas,
        "precisa_correcao": a.status in ("concluido", "expirado") and corrigidas < len(disc),
        # comportamento no DASH: resumo sempre presente + contagem de alertas
        "comportamento": comportamento,
        "alertas_comportamento": alertas,
        "criado_em": a.criado_em,
    }
    if com_respostas:
        respostas = {str(r.get("questao_id")): r for r in (a.respostas or [])}
        correcao = a.correcao_discursivas or {}
        d["questoes"] = []
        for q in questoes:
            r = respostas.get(str(q.id)) or {}
            item = {"id": str(q.id), "enunciado": q.enunciado, "tipo": q.tipo, "peso": q.peso}
            if q.tipo == "objetiva":
                item["opcoes"] = q.opcoes or []
                item["gabarito"] = q.gabarito   # RH VÊ o gabarito
                item["escolha"] = r.get("escolha")
                item["acertou"] = str(r.get("escolha")) == str(q.gabarito) if r else False
            else:
                item["resposta"] = r.get("texto") or ""
                item["correcao"] = correcao.get(str(q.id)) or {}
            d["questoes"].append(item)
        # comportamento já está no dump base (agora aparece no dash também)
    return d


@router.get("/rh/provas-aplicacoes", dependencies=[Depends(requer_rh)])
def listar_aplicacoes(prova_id: uuid.UUID | None = None, status: str | None = None,
                      db: Session = Depends(get_db)) -> list[dict]:
    q = select(AplicacaoProva).order_by(AplicacaoProva.criado_em.desc())
    if prova_id:
        q = q.where(AplicacaoProva.prova_id == prova_id)
    if status:
        q = q.where(AplicacaoProva.status == status)
    return [_dump_aplicacao_rh(db, a) for a in db.scalars(q).all()]


@router.get("/rh/provas-aplicacoes/{aid}", dependencies=[Depends(requer_rh)])
def detalhe_aplicacao(aid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    a = db.get(AplicacaoProva, aid)
    if a is None:
        raise HTTPException(status_code=404, detail="aplicacao_nao_encontrada")
    return _dump_aplicacao_rh(db, a, com_respostas=True)


class CorrecaoIn(BaseModel):
    # {questao_id: {nota: 0-100, comentario?}}
    correcao_discursivas: dict


@router.put("/rh/provas-aplicacoes/{aid}/correcao", dependencies=[Depends(requer_rh)])
def corrigir_discursivas(aid: uuid.UUID, payload: CorrecaoIn, db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(requer_rh)) -> dict:
    a = db.get(AplicacaoProva, aid)
    if a is None:
        raise HTTPException(status_code=404, detail="aplicacao_nao_encontrada")
    # só aceita correção para questões discursivas desta prova; clampa a nota 0-100
    disc_ids = {str(q.id) for q in _questoes(db, a.prova_id) if q.tipo == "discursiva"}
    limpo = {}
    for qid, c in (payload.correcao_discursivas or {}).items():
        if str(qid) not in disc_ids or not isinstance(c, dict):
            continue
        nota = c.get("nota")
        limpo[str(qid)] = {
            "nota": max(0.0, min(100.0, float(nota))) if nota is not None else None,
            "comentario": str(c.get("comentario") or "")[:1000] or None,
        }
    a.correcao_discursivas = limpo
    a.corrigido_por = rh.email
    a.corrigido_em = datetime.now(timezone.utc)
    _recalcular_nota_final(db, a)
    registrar(db, "prova_corrigida", ator="rh", ator_detalhe=rh.email,
              candidato_id=None, detalhe={"aplicacao": str(aid), "nota_final": a.nota_final})
    db.commit()
    return _dump_aplicacao_rh(db, a, com_respostas=True)
