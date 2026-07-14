"""Checklist de documentos do candidato: listar slots, enviar arquivo, concluir envio."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import base_url_publica, get_settings
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import SlotDocumento, StatusSlot, TipoDocumento
from app.services import storage
from app.services.auditoria import registrar
from app.services.email import enviar_email
from app.services.magic_link import resolver_token
from app.services.normalizacao import (ArquivoInvalido, normalizar_para_pdf,
                                       validar_comprovante_recente)
from app.services.slots import sincronizar_slots

router = APIRouter(tags=["documentos"])


def _candidato_do_token(token: str, db: Session) -> Candidato:
    candidato = resolver_token(db, token)
    if candidato is None:
        raise HTTPException(status_code=404, detail="link_invalido_ou_expirado")
    return candidato


def _slot_out(slot: SlotDocumento) -> dict:
    return {
        "id": slot.id,
        "tipo": slot.tipo,
        "dependente_id": slot.dependente_id,
        "obrigatorio": slot.obrigatorio,
        "status": slot.status,
        "motivo_rejeicao": slot.motivo_rejeicao,
        "motivo_rejeicao_obs": slot.motivo_rejeicao_obs,
        "paginas": slot.paginas,
        "enviado_em": slot.enviado_em,
    }


@router.get("/c/{token}/documentos")
def checklist(token: str, db: Session = Depends(get_db)) -> dict:
    """Sincroniza o catálogo com o estado atual da ficha e devolve o checklist."""
    candidato = _candidato_do_token(token, db)
    slots = sincronizar_slots(db, candidato)
    db.commit()
    obrigatorios = [s for s in slots if s.obrigatorio]
    ok = [s for s in obrigatorios if s.status in (StatusSlot.enviado, StatusSlot.aprovado)]
    return {
        "status_candidato": candidato.status,
        "progresso": {"ok": len(ok), "total": len(obrigatorios)},
        "slots": [_slot_out(s) for s in slots],
    }


@router.post("/c/{token}/documentos/{slot_id}/arquivo")
def enviar_arquivo(
    token: str,
    slot_id: uuid.UUID,
    arquivo: UploadFile,
    db: Session = Depends(get_db),
) -> dict:
    candidato = _candidato_do_token(token, db)
    if candidato.status == StatusCandidato.envio_concluido:
        raise HTTPException(status_code=409, detail="envio_ja_concluido")
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")

    dados = arquivo.file.read()
    try:
        pdf, paginas = normalizar_para_pdf(arquivo.filename or "arquivo", dados)
        if slot.tipo == TipoDocumento.comp_endereco:
            validar_comprovante_recente(arquivo.filename or "arquivo", dados, pdf)
    except ArquivoInvalido as exc:
        # Feedback imediato ao candidato: o front traduz o código em linguagem simples.
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    base = f"candidatos/{candidato.id}/slots/{slot.id}"
    storage.salvar(f"{base}/original/{arquivo.filename}", dados,
                   arquivo.content_type or "application/octet-stream")
    storage.salvar(f"{base}/documento.pdf", pdf, "application/pdf")

    slot.arquivo_original_key = f"{base}/original/{arquivo.filename}"
    slot.arquivo_pdf_key = f"{base}/documento.pdf"
    slot.paginas = paginas
    slot.status = StatusSlot.enviado
    slot.motivo_rejeicao = None
    slot.motivo_rejeicao_obs = None
    slot.enviado_em = datetime.now(timezone.utc)
    registrar(db, "documento_enviado", ator="candidato", candidato_id=candidato.id,
              detalhe={"tipo": slot.tipo.value, "paginas": paginas})
    if candidato.status in (StatusCandidato.aguardando_assinatura, StatusCandidato.preenchendo):
        candidato.status = StatusCandidato.docs_pendentes
    db.commit()
    return _slot_out(slot)


@router.post("/c/{token}/concluir-envio")
def concluir_envio(token: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Botão 'CONCLUÍ MEU ENVIO': congela o checklist e notifica o RH."""
    candidato = _candidato_do_token(token, db)
    slots = sincronizar_slots(db, candidato)
    faltando = [
        s.tipo for s in slots
        if s.obrigatorio and s.status not in (StatusSlot.enviado, StatusSlot.aprovado,
                                              StatusSlot.dispensado)
    ]
    if faltando:
        raise HTTPException(status_code=422, detail={"faltando": faltando})

    candidato.status = StatusCandidato.envio_concluido
    registrar(db, "envio_concluido", ator="candidato", candidato_id=candidato.id)
    db.commit()

    settings = get_settings()
    enviar_email(
        settings.smtp_from,
        f"📥 Documentação completa: {candidato.nome_completo}",
        f"O candidato {candidato.nome_completo} concluiu o envio da documentação.\n"
        f"Acesse o painel do RH para revisar: {base_url_publica(request)}/rh\n",
    )
    return {"status": candidato.status}
