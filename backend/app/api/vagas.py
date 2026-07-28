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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.match import (AnaliseTalento, ProcessamentoMatch,
                              StatusProcessamento)
from app.models.talento import Talento
from app.models.usuario_rh import UsuarioRH
from app.models.vaga import Vaga
from app.services.auditoria import registrar

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
    # True = ignora análises já feitas e refaz tudo (botão "reanalisar").
    # Por padrão REAPROVEITA o que já foi analisado para esta vaga — clicar
    # de novo é praticamente grátis (decisão do Bruno, 2026-07-28). Era a
    # repetição do custo que transformou 18 análises em 2 na 2ª rodada.
    reanalisar: bool = False


@router.post("/rh/vagas/{vaga_id}/ranquear", status_code=202)
def ranquear(vaga_id: uuid.UUID, payload: RanquearIn, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """ENFILEIRA o ranqueamento e devolve na hora (202) — o RH continua
    usando o sistema enquanto a análise roda em segundo plano.

    Antes (v1.99) isso era síncrono: 131 talentos com OCR jamais caberiam nos
    60s de timeout do nginx, e um único HTTP 429 desligava a IA para todos os
    talentos restantes. Agora o worker processa devagar, esperando a cota
    quando precisa, e o resultado aparece na aba Resultados."""
    from app.services import fila
    from app.workers.match import ranquear as tarefa_ranquear

    vaga = db.get(Vaga, vaga_id)
    if vaga is None:
        raise HTTPException(status_code=404, detail="vaga_nao_encontrada")

    # Já existe um processamento em andamento para esta vaga? Não empilha.
    em_andamento = db.scalar(select(ProcessamentoMatch).where(
        ProcessamentoMatch.vaga_id == vaga_id,
        ProcessamentoMatch.status.in_([StatusProcessamento.na_fila,
                                       StatusProcessamento.processando])))
    if em_andamento is not None:
        return {"processamento_id": em_andamento.id, "status": em_andamento.status.value,
                "ja_em_andamento": True}

    if not fila.fila_disponivel():
        raise HTTPException(status_code=503, detail="fila_indisponivel")

    proc = ProcessamentoMatch(vaga_id=vaga_id, solicitado_por=rh.email)
    db.add(proc)
    db.flush()
    registrar(db, "vaga_ranqueamento_enfileirado", ator="rh", ator_detalhe=rh.email,
              detalhe={"vaga": str(vaga_id), "processamento": str(proc.id),
                       "reanalisar": payload.reanalisar})
    db.commit()

    fila.enfileirar(tarefa_ranquear, str(proc.id), payload.reanalisar)
    return {"processamento_id": proc.id, "status": proc.status.value,
            "ja_em_andamento": False}


@router.get("/rh/curriculos/indexacao")
def status_indexacao(db: Session = Depends(get_db)) -> dict:
    """Quantos currículos já tiveram o texto extraído. O ranqueamento só
    consegue analisar quem está indexado — se este número estiver baixo, é
    aqui que está o gargalo, não na IA."""
    from app.models.match import CurriculoTexto

    total_talentos = db.scalar(select(func.count()).select_from(Talento)) or 0
    com_curriculo = db.scalar(select(func.count()).select_from(Talento)
                              .where(Talento.curriculo_key.isnot(None))) or 0
    indexados = db.scalar(select(func.count()).select_from(CurriculoTexto)
                          .where(CurriculoTexto.legivel.is_(True))) or 0
    ilegiveis = db.scalar(select(func.count()).select_from(CurriculoTexto)
                          .where(CurriculoTexto.legivel.is_(False),
                                 CurriculoTexto.motivo_falha.isnot(None),
                                 CurriculoTexto.motivo_falha != "sem_curriculo")) or 0
    return {"total_talentos": total_talentos, "com_curriculo": com_curriculo,
            "indexados": indexados, "ilegiveis": ilegiveis,
            "pendentes": max(0, com_curriculo - indexados - ilegiveis)}


@router.post("/rh/curriculos/indexar", status_code=202)
def enfileirar_backfill(db: Session = Depends(get_db),
                        rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Enfileira a extração de texto dos currículos que ainda não foram
    lidos (os que já estavam na base antes da v2.00). Roda em background,
    devagar — OCR tem custo."""
    from app.services import fila
    from app.workers.match import backfill_curriculos

    if not fila.fila_disponivel():
        raise HTTPException(status_code=503, detail="fila_indisponivel")
    fila.enfileirar(backfill_curriculos)
    registrar(db, "curriculos_backfill_enfileirado", ator="rh", ator_detalhe=rh.email)
    db.commit()
    return {"enfileirado": True}


@router.get("/rh/vagas/{vaga_id}/processamentos")
def listar_processamentos(vaga_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    """Histórico de ranqueamentos da vaga (a aba Resultados lista por aqui)."""
    procs = db.scalars(select(ProcessamentoMatch)
                       .where(ProcessamentoMatch.vaga_id == vaga_id)
                       .order_by(ProcessamentoMatch.criado_em.desc())).all()
    return [_dump_processamento(p) for p in procs]


def _dump_processamento(p: ProcessamentoMatch) -> dict:
    return {
        "id": p.id, "vaga_id": p.vaga_id, "status": p.status.value,
        "total_talentos": p.total_talentos, "processados": p.processados,
        "analisados_ia": p.analisados_ia, "reaproveitados": p.reaproveitados,
        "sem_curriculo": p.sem_curriculo, "ilegiveis": p.ilegiveis,
        "suspeitos": p.suspeitos, "observacao": p.observacao,
        "solicitado_por": p.solicitado_por,
        "criado_em": p.criado_em, "concluido_em": p.concluido_em,
    }


@router.get("/rh/vagas/{vaga_id}/resultado")
def resultado(vaga_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Resultado consolidado da vaga: o processamento mais recente + a lista
    de pessoas com o MOTIVO de cada uma estar onde está.

    Ninguém some em silêncio — quem não tem currículo, quem tem currículo
    ilegível e quem ficou sem análise por cota aparecem todos, identificados
    (mesma regra do lote de documento crítico)."""
    vaga = db.get(Vaga, vaga_id)
    if vaga is None:
        raise HTTPException(status_code=404, detail="vaga_nao_encontrada")

    proc = db.scalar(select(ProcessamentoMatch)
                     .where(ProcessamentoMatch.vaga_id == vaga_id)
                     .order_by(ProcessamentoMatch.criado_em.desc()).limit(1))

    analises = db.scalars(select(AnaliseTalento)
                          .where(AnaliseTalento.vaga_id == vaga_id)).all()
    talentos = {t.id: t for t in db.scalars(select(Talento))}

    itens = []
    for a in analises:
        t = talentos.get(a.talento_id)
        if t is None:
            continue
        itens.append({
            "talento_id": a.talento_id, "nome": t.nome,
            "cargo_interesse": t.cargo_interesse,
            "cidade": t.cidade, "telefone": t.telefone, "email": t.email,
            "resultado": a.resultado.value, "nota": a.nota,
            "atende_obrigatorios": a.atende_obrigatorios,
            "justificativa": a.justificativa, "bate_filtro": a.bate_filtro,
            "curriculo_suspeito": a.curriculo_suspeito,
            "detalhe_falha": a.detalhe_falha,
            "tem_curriculo": bool(t.curriculo_key),
            "status_talento": t.status.value,
        })

    # Ordena: nota desc (quem tem), depois quem bate o filtro estruturado.
    itens.sort(key=lambda i: (i["nota"] if i["nota"] is not None else -1,
                              i["bate_filtro"]), reverse=True)

    return {"vaga": _dump_vaga(vaga),
            "processamento": _dump_processamento(proc) if proc else None,
            "itens": itens}
