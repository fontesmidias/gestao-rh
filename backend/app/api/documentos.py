"""Checklist de documentos do candidato: listar slots, enviar arquivo, concluir envio."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
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
    sugestoes: dict = {}
    detectado: str | None = None
    try:
        pdf, paginas = normalizar_para_pdf(arquivo.filename or "arquivo", dados)
        if slot.tipo == TipoDocumento.comp_endereco:
            validar_comprovante_recente(arquivo.filename or "arquivo", dados, pdf)
        if slot.tipo == TipoDocumento.cpf_doc:
            _conferir_cpf_do_documento(db, candidato, arquivo.filename or "arquivo",
                                       dados, pdf)
        # OCR de qualquer documento com dados de ficha: SUGESTÕES ao candidato
        # (o front pergunta se ele quer usar — nada é aplicado sem consentimento).
        texto = _texto(arquivo.filename, dados, pdf)
        if texto:
            from app.services.ocr_rg import sugestoes_por_slot
            sugestoes, detectado = sugestoes_por_slot(slot.tipo.value, texto)
    except ArquivoInvalido as exc:
        # Feedback imediato ao candidato: o front traduz o código em linguagem simples.
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    _gravar_no_slot(db, candidato, slot, arquivo.filename, arquivo.content_type,
                    dados, pdf, paginas)
    db.commit()
    saida = _slot_out(slot)
    if sugestoes:
        saida["sugestoes"] = sugestoes
    if detectado:
        saida["documento_detectado"] = detectado
    return saida


def _texto(nome_arquivo: str | None, dados: bytes, pdf: bytes) -> str | None:
    from pathlib import Path as _P

    from app.services.normalizacao import _texto_do_envio
    return _texto_do_envio(_P((nome_arquivo or "a.jpg").lower()).suffix, dados, pdf)


def _gravar_no_slot(db: Session, candidato: Candidato, slot: SlotDocumento,
                    nome_arquivo: str | None, content_type: str | None,
                    dados: bytes, pdf: bytes, paginas: int) -> None:
    base = f"candidatos/{candidato.id}/slots/{slot.id}"
    storage.salvar(f"{base}/original/{nome_arquivo}", dados,
                   content_type or "application/octet-stream")
    storage.salvar(f"{base}/documento.pdf", pdf, "application/pdf")

    slot.arquivo_original_key = f"{base}/original/{nome_arquivo}"
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


@router.post("/c/{token}/documentos/identidade")
def enviar_identidade(token: str, arquivo: UploadFile,
                      db: Session = Depends(get_db)) -> dict:
    """Foto do RG OU da CNH (o candidato escolhe — muita gente só tem a CNH à
    mão): detecta qual dos dois é, guarda no slot certo do checklist e devolve
    as sugestões de preenchimento para o candidato conferir."""
    from app.services.ocr_rg import (detectar_tipo, sugestoes_da_cnh,
                                     sugestoes_do_rg)

    candidato = _candidato_do_token(token, db)
    if candidato.status == StatusCandidato.envio_concluido:
        raise HTTPException(status_code=409, detail="envio_ja_concluido")

    dados = arquivo.file.read()
    try:
        pdf, paginas = normalizar_para_pdf(arquivo.filename or "arquivo", dados)
    except ArquivoInvalido as exc:
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    texto = _texto(arquivo.filename, dados, pdf) or ""
    detectado = detectar_tipo(texto)
    e_cnh = detectado == "cnh"

    slots = {s.tipo: s for s in sincronizar_slots(db, candidato)}
    slot = slots.get(TipoDocumento.habilitacao_prof if e_cnh else TipoDocumento.rg) \
        or slots.get(TipoDocumento.rg)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")

    sugestoes = sugestoes_da_cnh(texto) if e_cnh else sugestoes_do_rg(texto)
    _gravar_no_slot(db, candidato, slot, arquivo.filename, arquivo.content_type,
                    dados, pdf, paginas)
    db.commit()
    saida = _slot_out(slot)
    saida["sugestoes"] = sugestoes
    saida["documento_detectado"] = detectado
    return saida


def _conferir_cpf_do_documento(db: Session, candidato: Candidato,
                               nome_arquivo: str, dados: bytes, pdf: bytes) -> None:
    """Se o documento de CPF traz um número legível e ele NÃO bate com o CPF da
    ficha, recusa na hora (documento de outra pessoa ou digitação errada).
    Sem leitura ou sem CPF na ficha, não bloqueia — o RH decide na revisão."""
    from pathlib import Path as _P

    from app.models.ficha import DocumentosIdentificacao
    from app.services.normalizacao import _texto_do_envio
    from app.services.ocr_rg import cpfs_no_texto

    doc = db.get(DocumentosIdentificacao, candidato.id)
    if doc is None or not doc.cpf:
        return
    texto = _texto_do_envio(_P(nome_arquivo.lower()).suffix, dados, pdf)
    achados = cpfs_no_texto(texto or "")
    if achados and doc.cpf not in achados:
        raise ArquivoInvalido("cpf_divergente")


@router.get("/c/{token}/documentos/{slot_id}/arquivo")
def ver_meu_arquivo(token: str, slot_id: uuid.UUID,
                    db: Session = Depends(get_db)) -> Response:
    """O candidato confere o que ele mesmo enviou (PDF normalizado)."""
    candidato = _candidato_do_token(token, db)
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id or slot.arquivo_pdf_key is None:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=storage.ler(slot.arquivo_pdf_key),
                    media_type="application/pdf")


@router.delete("/c/{token}/documentos/{slot_id}/arquivo")
def excluir_meu_arquivo(token: str, slot_id: uuid.UUID,
                        db: Session = Depends(get_db)) -> dict:
    """O candidato remove um envio seu que ainda não foi aprovado, para mandar
    outro no lugar. Antes de apagar, o hash do arquivo vai para a auditoria —
    o arquivo morre, a evidência de que existiu fica."""
    candidato = _candidato_do_token(token, db)
    if candidato.status in (StatusCandidato.envio_concluido, StatusCandidato.aprovado,
                            StatusCandidato.expurgado):
        raise HTTPException(status_code=409, detail="envio_ja_concluido")
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if slot.status not in (StatusSlot.enviado, StatusSlot.rejeitado):
        raise HTTPException(status_code=409, detail="arquivo_nao_pode_ser_excluido")

    expurgar_arquivos_do_slot(db, slot, evento="documento_excluido_candidato",
                              ator="candidato")
    slot.status = StatusSlot.pendente
    slot.motivo_rejeicao = None
    slot.motivo_rejeicao_obs = None
    slot.enviado_em = None
    slot.paginas = None
    db.commit()
    return _slot_out(slot)


def expurgar_arquivos_do_slot(db: Session, slot: SlotDocumento, evento: str,
                              ator: str, ator_detalhe: str | None = None) -> None:
    """Remove os arquivos do slot do storage, gravando ANTES na auditoria o
    hash SHA-256, tamanho e caminho de cada um (linha vermelha do projeto:
    nada some sem hash na auditoria)."""
    import hashlib

    evidencias = []
    for key in (slot.arquivo_pdf_key, slot.arquivo_original_key):
        if not key:
            continue
        try:
            dados = storage.ler(key)
            evidencias.append({"arquivo": key,
                               "sha256": hashlib.sha256(dados).hexdigest(),
                               "bytes": len(dados)})
        except Exception:
            evidencias.append({"arquivo": key, "sha256": "ilegivel_no_storage"})
    registrar(db, evento, ator=ator, ator_detalhe=ator_detalhe,
              candidato_id=slot.candidato_id,
              detalhe={"tipo": slot.tipo.value, "arquivos": evidencias})
    for key in (slot.arquivo_pdf_key, slot.arquivo_original_key):
        if key:
            try:
                storage.remover(key)
            except Exception:
                pass  # storage indisponível: a auditoria registrou; expurgo pega depois
    slot.arquivo_pdf_key = None
    slot.arquivo_original_key = None


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
