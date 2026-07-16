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
from app.services.normalizacao import (ArquivoInvalido, combinar_pdfs,
                                       normalizar_para_pdf,
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
    arquivo: UploadFile | None = None,
    arquivos: list[UploadFile] | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """Aceita UM arquivo (campo `arquivo`) ou VÁRIOS (`arquivos`: frente e
    verso, páginas de certidão…) — tudo vira um único PDF no slot, e o OCR lê
    o texto combinado (o verso do RG é onde mora a filiação)."""
    candidato = _candidato_do_token(token, db)
    if candidato.status == StatusCandidato.envio_concluido:
        raise HTTPException(status_code=409, detail="envio_ja_concluido")
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")

    lista = ([arquivo] if arquivo is not None else []) + (arquivos or [])
    if not lista:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    sugestoes: dict = {}
    detectado: str | None = None
    try:
        partes = []  # (nome, content_type, dados, pdf)
        for up in lista:
            dados = up.file.read()
            pdf, _ = normalizar_para_pdf(up.filename or "arquivo", dados)
            if slot.tipo == TipoDocumento.comp_endereco:
                validar_comprovante_recente(up.filename or "arquivo", dados, pdf)
            partes.append((up.filename or "arquivo", up.content_type, dados, pdf))

        texto = "\n".join(filter(None, (_texto(n, d, p) for n, _, d, p in partes)))
        if slot.tipo == TipoDocumento.cpf_doc:
            _conferir_cpf_no_texto(db, candidato, texto)
        # OCR de qualquer documento com dados de ficha: SUGESTÕES ao candidato
        # (o front pergunta se ele quer usar — nada é aplicado sem consentimento).
        if texto:
            from app.services.ocr_rg import sugestoes_por_slot
            sugestoes, detectado = sugestoes_por_slot(slot.tipo.value, texto)
        pdf_final, paginas = combinar_pdfs([p[3] for p in partes])
    except ArquivoInvalido as exc:
        # Feedback imediato ao candidato: o front traduz o código em linguagem simples.
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    _gravar_partes_no_slot(db, candidato, slot, partes, pdf_final, paginas)
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
    _gravar_partes_no_slot(db, candidato, slot,
                           [(nome_arquivo or "arquivo", content_type, dados, None)],
                           pdf, paginas)


def _gravar_partes_no_slot(db: Session, candidato: Candidato, slot: SlotDocumento,
                           partes: list[tuple], pdf_final: bytes, paginas: int) -> None:
    """Grava 1..N originais + o PDF combinado do slot. Um reenvio primeiro
    expurga (com hash em auditoria) o que havia antes — nada fica órfão."""
    if slot.arquivo_pdf_key:
        expurgar_arquivos_do_slot(db, slot, evento="documento_substituido",
                                  ator="candidato")
    base = f"candidatos/{candidato.id}/slots/{slot.id}"
    for i, (nome, content_type, dados, _pdf) in enumerate(partes, start=1):
        storage.salvar(f"{base}/original/{i}-{nome}", dados,
                       content_type or "application/octet-stream")
    storage.salvar(f"{base}/documento.pdf", pdf_final, "application/pdf")

    slot.arquivo_original_key = f"{base}/original/1-{partes[0][0]}"
    slot.arquivo_pdf_key = f"{base}/documento.pdf"
    slot.paginas = paginas
    slot.status = StatusSlot.enviado
    slot.motivo_rejeicao = None
    slot.motivo_rejeicao_obs = None
    slot.enviado_em = datetime.now(timezone.utc)
    registrar(db, "documento_enviado", ator="candidato", candidato_id=candidato.id,
              detalhe={"tipo": slot.tipo.value, "paginas": paginas,
                       "arquivos": len(partes)})
    if candidato.status in (StatusCandidato.aguardando_assinatura, StatusCandidato.preenchendo):
        candidato.status = StatusCandidato.docs_pendentes


@router.post("/c/{token}/documentos/identidade")
def enviar_identidade(token: str,
                      arquivo: UploadFile | None = None,
                      arquivos: list[UploadFile] | None = None,
                      db: Session = Depends(get_db)) -> dict:
    """Foto(s) do RG OU da CNH (frente e verso quando houver): detecta qual dos
    dois é, guarda tudo como um PDF no slot certo do checklist e devolve as
    sugestões de preenchimento — a filiação e a expedição moram no verso."""
    from app.services.ocr_rg import (detectar_tipo, sugestoes_da_cnh,
                                     sugestoes_do_rg)

    candidato = _candidato_do_token(token, db)
    if candidato.status == StatusCandidato.envio_concluido:
        raise HTTPException(status_code=409, detail="envio_ja_concluido")

    lista = ([arquivo] if arquivo is not None else []) + (arquivos or [])
    if not lista:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    try:
        partes = []
        for up in lista:
            dados = up.file.read()
            pdf, _ = normalizar_para_pdf(up.filename or "arquivo", dados)
            partes.append((up.filename or "arquivo", up.content_type, dados, pdf))
        pdf_final, paginas = combinar_pdfs([p[3] for p in partes])
    except ArquivoInvalido as exc:
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    texto = "\n".join(filter(None, (_texto(n, d, p) for n, _, d, p in partes)))
    detectado = detectar_tipo(texto)
    e_cnh = detectado == "cnh"

    slots = {s.tipo: s for s in sincronizar_slots(db, candidato)}
    slot = slots.get(TipoDocumento.habilitacao_prof if e_cnh else TipoDocumento.rg) \
        or slots.get(TipoDocumento.rg)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")

    sugestoes = sugestoes_da_cnh(texto) if e_cnh else sugestoes_do_rg(texto)
    _gravar_partes_no_slot(db, candidato, slot, partes, pdf_final, paginas)
    db.commit()
    saida = _slot_out(slot)
    saida["sugestoes"] = sugestoes
    saida["documento_detectado"] = detectado
    return saida


def _conferir_cpf_no_texto(db: Session, candidato: Candidato, texto: str) -> None:
    """Se o documento de CPF traz um número legível e ele NÃO bate com o CPF da
    ficha, recusa na hora (documento de outra pessoa ou digitação errada).
    Sem leitura ou sem CPF na ficha, não bloqueia — o RH decide na revisão."""
    from app.models.ficha import DocumentosIdentificacao
    from app.services.ocr_rg import cpfs_no_texto

    doc = db.get(DocumentosIdentificacao, candidato.id)
    if doc is None or not doc.cpf:
        return
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
    """Remove TODOS os arquivos do slot do storage (PDF combinado + originais,
    inclusive frente/verso), gravando ANTES na auditoria o hash SHA-256,
    tamanho e caminho de cada um (linha vermelha do projeto: nada some sem
    hash na auditoria)."""
    import hashlib

    base = f"candidatos/{slot.candidato_id}/slots/{slot.id}/"
    try:
        keys = storage.listar(base)
    except Exception:
        keys = [k for k in (slot.arquivo_pdf_key, slot.arquivo_original_key) if k]

    evidencias = []
    for key in keys:
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
    for key in keys:
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
