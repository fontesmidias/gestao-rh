"""Links de testagem — aplicação avulsa dos testes (DISC + situacional).

Fluxo do participante (link público /t/{token}):
1. GET  /t/{token} — o link existe e está ativo?
2. POST /t/{token}/participar — só o NOME (sem CPF/e-mail/2FA); cria os dois
   testes e devolve o id do participante (guardado no navegador para retomada).
3. iniciar → questoes → responder → concluir, igual ao teste do candidato
   (mesmos timers e a mesma pontuação no servidor — o gabarito nunca sai dele).
4. GET resultados — aqui o participante VÊ o próprio resultado: é ambiente de
   testagem/validação do instrumento, não de seleção (diferente da admissão,
   onde o resultado é restrito ao RH).

O RH gerencia em /rh/testagem/links: cria, ativa/desativa e acompanha os
participantes com os resultados completos."""

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
from app.models.teste import StatusTeste, TipoTeste
from app.models.testagem import LinkTestagem, ParticipanteTestagem, TesteTestagem
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.disc import (PERFIS_DISC, TEMPO_DISC_SEGUNDOS,
                               TEMPO_SITUACIONAL_SEGUNDOS, pontuar_disc,
                               pontuar_situacional, questoes_disc_publicas,
                               questoes_situacional_publicas)
from app.services.limite import exigir

router = APIRouter(tags=["testagem"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _link(token: str, db: Session, exigir_ativo: bool = True) -> LinkTestagem:
    link = db.scalar(select(LinkTestagem).where(LinkTestagem.token == token))
    if link is None:
        raise HTTPException(status_code=404, detail="link_invalido")
    if exigir_ativo and not link.ativo:
        raise HTTPException(status_code=403, detail="link_desativado")
    return link


def _participante(link: LinkTestagem, pid: uuid.UUID, db: Session) -> ParticipanteTestagem:
    p = db.get(ParticipanteTestagem, pid)
    if p is None or p.link_id != link.id:
        raise HTTPException(status_code=404, detail="participante_nao_encontrado")
    return p


def _testes(db: Session, p: ParticipanteTestagem) -> list[TesteTestagem]:
    return db.scalars(select(TesteTestagem)
                      .where(TesteTestagem.participante_id == p.id)
                      .order_by(TesteTestagem.criado_em)).all()


def _pontuar(t: TesteTestagem) -> dict:
    return (pontuar_disc(t.respostas or []) if t.tipo == TipoTeste.disc
            else pontuar_situacional(t.respostas or []))


def _expira_se_estourou(db: Session, t: TesteTestagem) -> None:
    if (t.status == StatusTeste.em_andamento and t.prazo_ate
            and t.prazo_ate < datetime.now(timezone.utc)):
        t.resultado = _pontuar(t)
        t.status = StatusTeste.expirado
        t.concluido_em = datetime.now(timezone.utc)
        db.commit()


def _dump(t: TesteTestagem) -> dict:
    restante = None
    if t.status == StatusTeste.em_andamento and t.prazo_ate:
        restante = max(0, int((t.prazo_ate - datetime.now(timezone.utc)).total_seconds()))
    return {"tipo": t.tipo, "status": t.status, "segundos_restantes": restante,
            "respondidas": len(t.respostas or [])}


def _dump_resultado(t: TesteTestagem) -> dict:
    from app.api.testes import _resumo_eventos
    return {"tipo": t.tipo, "status": t.status,
            "respondidas": len(t.respostas or []),
            "iniciado_em": t.iniciado_em, "concluido_em": t.concluido_em,
            "resultado": t.resultado or None,
            "comportamento": _resumo_eventos(t.eventos or []),
            "eventos": t.eventos or []}


# ---------------------------------------------------------------------------
# Participante (público)
# ---------------------------------------------------------------------------


@router.get("/t/{token}")
def info_link(token: str, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db, exigir_ativo=False)
    return {"nome": link.nome, "ativo": link.ativo}


class ParticiparIn(BaseModel):
    nome: str


@router.post("/t/{token}/participar", status_code=201)
def participar(token: str, payload: ParticiparIn, request: Request,
               db: Session = Depends(get_db)) -> dict:
    nome = payload.nome.strip()
    if len(nome) < 3:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    exigir(f"testagem:ip:{ip_do_cliente(request) or '?'}", maximo=20, janela_s=3600)
    link = _link(token, db)
    p = ParticipanteTestagem(link_id=link.id, nome=nome[:200])
    db.add(p)
    db.flush()
    for tipo in (TipoTeste.disc, TipoTeste.situacional):
        db.add(TesteTestagem(participante_id=p.id, tipo=tipo))
    registrar(db, "testagem_participante_criado", ator="participante",
              detalhe={"link": link.nome, "nome": nome[:200]})
    db.commit()
    return {"participante_id": p.id}


@router.get("/t/{token}/p/{pid}")
def sessao(token: str, pid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    p = _participante(link, pid, db)
    testes = _testes(db, p)
    for t in testes:
        _expira_se_estourou(db, t)
    pendentes = [t for t in testes
                 if t.status in (StatusTeste.pendente, StatusTeste.em_andamento)]
    return {"nome": p.nome, "pendentes": [_dump(t) for t in pendentes],
            "todos_concluidos": bool(testes) and not pendentes}


def _teste_do_tipo(db: Session, p: ParticipanteTestagem, tipo: str) -> TesteTestagem:
    try:
        tipo_enum = TipoTeste(tipo)
    except ValueError:
        raise HTTPException(status_code=422, detail="tipo_invalido")
    t = db.scalar(select(TesteTestagem).where(
        TesteTestagem.participante_id == p.id, TesteTestagem.tipo == tipo_enum))
    if t is None:
        raise HTTPException(status_code=404, detail="teste_nao_encontrado")
    _expira_se_estourou(db, t)
    return t


@router.post("/t/{token}/p/{pid}/{tipo}/iniciar")
def iniciar(token: str, pid: uuid.UUID, tipo: str, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    p = _participante(link, pid, db)
    t = _teste_do_tipo(db, p, tipo)
    if t.status == StatusTeste.em_andamento:
        return _dump(t)  # retomada (recarregou a página)
    if t.status != StatusTeste.pendente:
        raise HTTPException(status_code=409, detail="teste_ja_realizado")
    segundos = TEMPO_DISC_SEGUNDOS if t.tipo == TipoTeste.disc else TEMPO_SITUACIONAL_SEGUNDOS
    t.status = StatusTeste.em_andamento
    t.iniciado_em = datetime.now(timezone.utc)
    t.prazo_ate = t.iniciado_em + timedelta(seconds=segundos)
    db.commit()
    return _dump(t)


@router.get("/t/{token}/p/{pid}/{tipo}/questoes")
def questoes(token: str, pid: uuid.UUID, tipo: str, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    p = _participante(link, pid, db)
    t = _teste_do_tipo(db, p, tipo)
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    qs = (questoes_disc_publicas() if t.tipo == TipoTeste.disc
          else questoes_situacional_publicas())
    return {"questoes": qs, **_dump(t)}


class RespostaIn(BaseModel):
    questao: int
    mais: str | None = None
    menos: str | None = None
    escolha: str | None = None


@router.post("/t/{token}/p/{pid}/{tipo}/responder")
def responder(token: str, pid: uuid.UUID, tipo: str, payload: RespostaIn,
              db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    p = _participante(link, pid, db)
    t = _teste_do_tipo(db, p, tipo)
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    if t.tipo == TipoTeste.disc:
        if not payload.mais or not payload.menos or payload.mais == payload.menos:
            raise HTTPException(status_code=422, detail="marque_mais_e_menos_diferentes")
        nova = {"questao": payload.questao, "mais": payload.mais, "menos": payload.menos}
    else:
        if not payload.escolha:
            raise HTTPException(status_code=422, detail="escolha_obrigatoria")
        nova = {"questao": payload.questao, "escolha": payload.escolha}
    respostas = [r for r in (t.respostas or []) if r.get("questao") != payload.questao]
    respostas.append(nova)
    t.respostas = respostas
    db.commit()
    return {"respondidas": len(respostas)}


@router.post("/t/{token}/p/{pid}/{tipo}/concluir")
def concluir(token: str, pid: uuid.UUID, tipo: str, db: Session = Depends(get_db)) -> dict:
    link = _link(token, db)
    p = _participante(link, pid, db)
    t = _teste_do_tipo(db, p, tipo)
    if t.status == StatusTeste.expirado:
        return {"status": t.status}
    if t.status != StatusTeste.em_andamento:
        raise HTTPException(status_code=409, detail="teste_nao_iniciado")
    t.resultado = _pontuar(t)
    t.status = StatusTeste.concluido
    t.concluido_em = datetime.now(timezone.utc)
    db.commit()
    return {"status": t.status}


class EventosIn(BaseModel):
    eventos: list[dict]


_MAX_EVENTOS = 800  # mesmo teto do teste da admissão


@router.post("/t/{token}/p/{pid}/{tipo}/eventos", status_code=204)
def registrar_eventos(token: str, pid: uuid.UUID, tipo: str, payload: EventosIn,
                      db: Session = Depends(get_db)) -> None:
    """Telemetria de comportamento na testagem (mesmo formato da admissão)."""
    link = _link(token, db)
    p = _participante(link, pid, db)
    t = _teste_do_tipo(db, p, tipo)
    if t.status not in (StatusTeste.em_andamento, StatusTeste.concluido,
                        StatusTeste.expirado):
        return
    atuais = list(t.eventos or [])
    for ev in payload.eventos[: _MAX_EVENTOS - len(atuais)]:
        if isinstance(ev, dict) and ev.get("e"):
            atuais.append({"t": round(float(ev.get("t") or 0), 1),
                           "e": str(ev["e"])[:40],
                           **({"d": str(ev["d"])[:120]} if ev.get("d") else {})})
    t.eventos = atuais
    db.commit()


@router.get("/t/{token}/p/{pid}/resultados")
def resultados(token: str, pid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Na testagem o PARTICIPANTE vê o resultado (diferente da admissão)."""
    link = _link(token, db)
    p = _participante(link, pid, db)
    testes = _testes(db, p)
    for t in testes:
        _expira_se_estourou(db, t)
    prontos = [t for t in testes
               if t.status in (StatusTeste.concluido, StatusTeste.expirado)]
    return {"nome": p.nome, "testes": [_dump_resultado(t) for t in prontos],
            "perfis": PERFIS_DISC}


# ---------------------------------------------------------------------------
# RH — gestão dos links e acompanhamento
# ---------------------------------------------------------------------------


def _dump_link(db: Session, link: LinkTestagem, base_url: str) -> dict:
    participantes = db.scalars(select(ParticipanteTestagem)
                               .where(ParticipanteTestagem.link_id == link.id)).all()
    concluidos = 0
    for p in participantes:
        testes = _testes(db, p)
        if testes and all(t.status in (StatusTeste.concluido, StatusTeste.expirado)
                          for t in testes):
            concluidos += 1
    return {"id": link.id, "nome": link.nome, "ativo": link.ativo,
            "criado_em": link.criado_em, "criado_por": link.criado_por,
            "url": f"{base_url}/t/{link.token}",
            "participantes": len(participantes), "concluidos": concluidos}


@router.get("/rh/testagem/links")
def listar_links(request: Request, db: Session = Depends(get_db),
                 _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    base = base_url_publica(request)
    links = db.scalars(select(LinkTestagem).order_by(LinkTestagem.criado_em.desc())).all()
    return {"links": [_dump_link(db, l, base) for l in links]}


class NovoLinkIn(BaseModel):
    nome: str


@router.post("/rh/testagem/links", status_code=201)
def criar_link(payload: NovoLinkIn, request: Request, db: Session = Depends(get_db),
               _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(status_code=422, detail="nome_obrigatorio")
    link = LinkTestagem(nome=nome[:120], token=secrets.token_urlsafe(16),
                        criado_por=_rh.email)
    db.add(link)
    registrar(db, "testagem_link_criado", ator="rh", ator_detalhe=_rh.email,
              detalhe={"nome": nome[:120]})
    db.commit()
    return _dump_link(db, link, base_url_publica(request))


class EditarLinkIn(BaseModel):
    ativo: bool | None = None
    nome: str | None = None


@router.put("/rh/testagem/links/{link_id}")
def editar_link(link_id: uuid.UUID, payload: EditarLinkIn, request: Request,
                db: Session = Depends(get_db),
                _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    link = db.get(LinkTestagem, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="link_nao_encontrado")
    if payload.ativo is not None:
        link.ativo = payload.ativo
    if payload.nome is not None and payload.nome.strip():
        link.nome = payload.nome.strip()[:120]
    registrar(db, "testagem_link_editado", ator="rh", ator_detalhe=_rh.email,
              detalhe={"nome": link.nome, "ativo": link.ativo})
    db.commit()
    return _dump_link(db, link, base_url_publica(request))


@router.post("/rh/testagem/participantes/{pid}/testes/{tipo}/resetar")
def resetar_teste_testagem(pid: uuid.UUID, tipo: str, db: Session = Depends(get_db),
                           _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Zera o teste do participante para refazer (resultado antigo na auditoria)."""
    p = db.get(ParticipanteTestagem, pid)
    if p is None:
        raise HTTPException(status_code=404, detail="participante_nao_encontrado")
    t = _teste_do_tipo(db, p, tipo)
    registrar(db, "testagem_teste_resetado", ator="rh", ator_detalhe=_rh.email,
              detalhe={"participante": p.nome, "tipo": tipo,
                       "status_anterior": t.status.value,
                       "resultado_anterior": t.resultado or None})
    t.status = StatusTeste.pendente
    t.respostas = []
    t.resultado = {}
    t.eventos = []
    t.iniciado_em = None
    t.prazo_ate = None
    t.concluido_em = None
    db.commit()
    return {"tipo": t.tipo, "status": t.status}


@router.get("/rh/testagem/links/{link_id}/participantes")
def participantes_do_link(link_id: uuid.UUID, db: Session = Depends(get_db),
                          _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    link = db.get(LinkTestagem, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="link_nao_encontrado")
    participantes = db.scalars(select(ParticipanteTestagem)
                               .where(ParticipanteTestagem.link_id == link.id)
                               .order_by(ParticipanteTestagem.criado_em.desc())).all()
    saida = []
    for p in participantes:
        testes = _testes(db, p)
        for t in testes:
            _expira_se_estourou(db, t)
        saida.append({"id": p.id, "nome": p.nome, "criado_em": p.criado_em,
                      "testes": [_dump_resultado(t) for t in testes]})
    return {"link": {"id": link.id, "nome": link.nome, "ativo": link.ativo},
            "participantes": saida, "perfis": PERFIS_DISC}
