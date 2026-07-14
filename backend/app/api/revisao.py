"""Painel do RH: lista de candidatos, revisão de documentos e dossiê."""

import unicodedata
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import get_settings
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import MotivoRejeicao, SlotDocumento, StatusSlot
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.dossie import DossieIncompleto, gerar_dossie
from app.services.email import enviar_email

router = APIRouter(tags=["revisao-rh"], dependencies=[Depends(requer_rh)])


@router.get("/rh/candidatos")
def listar_candidatos(db: Session = Depends(get_db)) -> list[dict]:
    candidatos = db.scalars(select(Candidato).order_by(Candidato.criado_em.desc())).all()
    slots = db.scalars(select(SlotDocumento)).all()
    por_candidato: dict[uuid.UUID, list[SlotDocumento]] = {}
    for s in slots:
        por_candidato.setdefault(s.candidato_id, []).append(s)
    saida = []
    for cand in candidatos:
        meus = [s for s in por_candidato.get(cand.id, []) if s.obrigatorio]
        ok = [s for s in meus if s.status in (StatusSlot.aprovado, StatusSlot.dispensado)]
        saida.append({
            "id": cand.id,
            "nome_completo": cand.nome_completo,
            "email": cand.email,
            "status": cand.status,
            "progresso_docs": {"ok": len(ok), "total": len(meus)},
            "criado_em": cand.criado_em,
            "dossie_gerado_em": cand.dossie_gerado_em,
        })
    return saida


@router.get("/rh/candidatos/{candidato_id}")
def detalhe_candidato(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    slots = db.scalars(
        select(SlotDocumento)
        .where(SlotDocumento.candidato_id == cand.id)
        .order_by(SlotDocumento.criado_em)
    ).all()
    return {
        "id": cand.id,
        "nome_completo": cand.nome_completo,
        "email": cand.email,
        "celular_whatsapp": cand.celular_whatsapp,
        "status": cand.status,
        "dossie_gerado_em": cand.dossie_gerado_em,
        "slots": [
            {
                "id": s.id,
                "tipo": s.tipo,
                "dependente_id": s.dependente_id,
                "obrigatorio": s.obrigatorio,
                "status": s.status,
                "motivo_rejeicao": s.motivo_rejeicao,
                "paginas": s.paginas,
                "enviado_em": s.enviado_em,
                "revisado_em": s.revisado_em,
            }
            for s in slots
        ],
    }


@router.get("/rh/slots/{slot_id}/arquivo")
def ver_arquivo(slot_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.arquivo_pdf_key is None:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=storage.ler(slot.arquivo_pdf_key), media_type="application/pdf")


def _ascii(texto: str) -> str:
    """Nome de arquivo seguro para header HTTP (só ASCII)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.replace(" ", "-")


def _slot_para_revisar(slot_id: uuid.UUID, db: Session) -> SlotDocumento:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if slot.status != StatusSlot.enviado:
        raise HTTPException(status_code=409, detail="slot_nao_esta_em_analise")
    return slot


@router.post("/rh/slots/{slot_id}/aprovar")
def aprovar(slot_id: uuid.UUID, db: Session = Depends(get_db),
            rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = _slot_para_revisar(slot_id, db)
    slot.status = StatusSlot.aprovado
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    registrar(db, "documento_aprovado", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id, detalhe={"tipo": slot.tipo.value})
    db.commit()
    return {"status": slot.status}


class RejeicaoIn(BaseModel):
    motivo: MotivoRejeicao
    observacao: str | None = None


_MOTIVO_LEGIVEL = {
    MotivoRejeicao.ilegivel: "a imagem ficou ilegível",
    MotivoRejeicao.doc_errado: "o documento enviado não é o solicitado",
    MotivoRejeicao.vencido: "o documento está vencido",
    MotivoRejeicao.incompleto: "o documento está incompleto (falta frente ou verso)",
    MotivoRejeicao.outro: "houve um problema com o arquivo",
}


@router.post("/rh/slots/{slot_id}/rejeitar")
def rejeitar(slot_id: uuid.UUID, payload: RejeicaoIn, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = _slot_para_revisar(slot_id, db)
    slot.status = StatusSlot.rejeitado
    slot.motivo_rejeicao = payload.motivo
    slot.motivo_rejeicao_obs = payload.observacao
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id

    candidato = db.get(Candidato, slot.candidato_id)
    # Reabre o checklist para o candidato corrigir.
    if candidato.status == StatusCandidato.envio_concluido:
        candidato.status = StatusCandidato.docs_pendentes
    registrar(db, "documento_rejeitado", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id,
              detalhe={"tipo": slot.tipo.value, "motivo": payload.motivo.value})
    db.commit()

    enviar_email(
        candidato.email,
        "🌱 Green House — um documento precisa ser reenviado",
        f"Olá, {candidato.nome_completo.split()[0].title()}!\n\n"
        f"Um dos seus documentos precisa ser enviado novamente: "
        f"{_MOTIVO_LEGIVEL[payload.motivo]}"
        + (f" ({payload.observacao})" if payload.observacao else "")
        + ".\n\nAcesse o mesmo link da sua admissão e reenvie apenas esse documento.\n",
    )
    return {"status": slot.status}


@router.post("/rh/slots/{slot_id}/dispensar")
def dispensar(slot_id: uuid.UUID, db: Session = Depends(get_db),
              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if slot.status == StatusSlot.aprovado:
        raise HTTPException(status_code=409, detail="slot_ja_aprovado")
    slot.status = StatusSlot.dispensado
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    db.commit()
    return {"status": slot.status}


@router.post("/rh/candidatos/{candidato_id}/dossie")
def gerar_dossie_endpoint(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    try:
        gerar_dossie(db, cand)
    except DossieIncompleto as exc:
        raise HTTPException(status_code=422, detail={"pendencias": exc.pendencias}) from exc
    cand.status = StatusCandidato.aprovado
    registrar(db, "dossie_gerado", ator="rh", candidato_id=cand.id)
    db.commit()

    settings = get_settings()
    enviar_email(
        settings.smtp_from,
        f"📄 Dossiê de admissão pronto: {cand.nome_completo}",
        f"O dossiê completo de {cand.nome_completo} foi gerado.\n"
        f"Baixe no painel: {settings.base_url}/rh\n",
    )
    return {"status": cand.status, "dossie_gerado_em": cand.dossie_gerado_em}


@router.get("/rh/candidatos/{candidato_id}/dossie")
def baixar_dossie(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    cand = db.get(Candidato, candidato_id)
    if cand is None or cand.dossie_pdf_key is None:
        raise HTTPException(status_code=404, detail="dossie_nao_gerado")
    return Response(
        content=storage.ler(cand.dossie_pdf_key),
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="dossie-{_ascii(cand.nome_completo)}.pdf"'},
    )
