"""Checklist de documentos do candidato: listar slots, enviar arquivo, concluir envio."""

import logging
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
from app.services.magic_link import resolver_token
from app.services.normalizacao import (ArquivoInvalido, combinar_pdfs,
                                       normalizar_para_pdf,
                                       validar_comprovante_recente)
from app.services.slots import sincronizar_slots

log = logging.getLogger(__name__)
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
    if candidato.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="admissao_encerrada")
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    # Reabertura CIRÚRGICA pós-aprovação (feedback 2026-07-24): um candidato já
    # APROVADO só pode reenviar um slot que o RH REJEITOU — nunca mexer num slot
    # já aprovado nem reabrir a ficha inteira. O status `aprovado` fica intacto
    # (não desfaz dossiê/efetivação); o RH reavalia só aquele documento.
    if (candidato.status == StatusCandidato.aprovado
            and slot.status != StatusSlot.rejeitado):
        raise HTTPException(status_code=409, detail="apenas_documento_rejeitado")

    lista = ([arquivo] if arquivo is not None else []) + (arquivos or [])
    if not lista:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    sugestoes: dict = {}
    detectado: str | None = None
    try:
        partes = []  # (nome, content_type, dados, pdf)
        for up in lista:
            dados = up.file.read()
            pdf, _ = normalizar_para_pdf(up.filename or "arquivo", dados,
                                         rotulo=slot.tipo.value)
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
    if candidato.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="admissao_encerrada")

    lista = ([arquivo] if arquivo is not None else []) + (arquivos or [])
    if not lista:
        raise HTTPException(status_code=422, detail="arquivo_vazio")

    try:
        partes = []
        for up in lista:
            dados = up.file.read()
            pdf, _ = normalizar_para_pdf(up.filename or "arquivo", dados,
                                         rotulo="documento de identidade")
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
    # Mesma contenção cirúrgica do enviar_arquivo: um aprovado só reenvia RG/CNH
    # se aquele slot foi rejeitado — não pode substituir um já aprovado.
    if (candidato.status == StatusCandidato.aprovado
            and slot.status != StatusSlot.rejeitado):
        raise HTTPException(status_code=409, detail="apenas_documento_rejeitado")

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
    """O candidato confere o documento como o RH o recebe (PDF no timbrado)."""
    candidato = _candidato_do_token(token, db)
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id or slot.arquivo_pdf_key is None:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    return Response(content=storage.ler(slot.arquivo_pdf_key),
                    media_type="application/pdf")


# O que TODO navegador exibe sem ajuda. O resto (HEIC do iPhone, Word) é
# convertido ao SERVIR — mesma decisão da v2.33 no currículo do talento.
_CT_EXIBIVEL = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}


def _originais_do_slot(slot: SlotDocumento) -> list[tuple[int, str, str]]:
    """(indice, nome, key) dos arquivos ORIGINAIS do slot, em ordem de envio.

    Os originais são gravados como `original/{i}-{nome}` (frente, verso,
    páginas…), mas o registro guarda a key de UM só (`arquivo_original_key`, o
    primeiro) — então a lista vem do storage, não do banco. A ordem é pelo
    número do prefixo, nunca a lexicográfica do listar: com 10 partes, "10-"
    viria antes de "2-" e o verso apareceria no lugar da frente.
    """
    base = f"candidatos/{slot.candidato_id}/slots/{slot.id}/original/"
    itens: list[tuple[int, str, str]] = []
    try:
        keys = storage.listar(base)
    except Exception:
        # Silêncio aqui viraria "você não enviou nada" para quem enviou — a
        # lição da v2.02: catch que engole falha de INFRA mente para o usuário.
        log.exception("Falha ao listar %s; caindo na key do registro", base)
        keys = []
    for key in keys:
        num, _, nome = key[len(base):].partition("-")
        if num.isdigit() and nome:
            itens.append((int(num), nome, key))
    if not itens and slot.arquivo_original_key:
        # Envio antigo, ou storage que não listou: ao menos o primeiro arquivo.
        # O nome sai do MESMO recorte usado acima — `rsplit("-")` perderia
        # metade de "1-doc-frente.jpg".
        _, _, nome = slot.arquivo_original_key.rpartition("/original/")[2].partition("-")
        itens.append((1, nome or "documento", slot.arquivo_original_key))
    itens.sort(key=lambda t: t[0])
    return itens


@router.get("/c/{token}/documentos/{slot_id}/originais")
def meus_originais(token: str, slot_id: uuid.UUID,
                   db: Session = Depends(get_db)) -> dict:
    """Lista o que a pessoa enviou neste slot — uma foto, frente e verso, ou as
    páginas de uma certidão. Consultada só quando ela pede para ver; sair
    perguntando ao storage a cada abertura do checklist seria uma chamada ao
    MinIO por documento da lista."""
    candidato = _candidato_do_token(token, db)
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    return {"arquivos": [{"indice": i, "nome": nome}
                         for i, nome, _ in _originais_do_slot(slot)],
            "tem_pdf": slot.arquivo_pdf_key is not None}


@router.get("/c/{token}/documentos/{slot_id}/original/{indice}")
def ver_meu_original(token: str, slot_id: uuid.UUID, indice: int,
                     db: Session = Depends(get_db)) -> Response:
    """Serve o arquivo COMO A PESSOA ENVIOU — a foto dela, não o PDF que o
    sistema montou.

    O PDF do slot é a foto reduzida e centralizada numa página A4 no papel
    timbrado: serve para o dossiê do RH, mas é o lugar errado para alguém
    conferir se a própria foto ficou legível, que é o que ela quer saber antes
    de concluir o envio.

    O arquivo é escolhido pelo ÍNDICE, resolvido contra a listagem do storage —
    nome de arquivo é texto do usuário e nunca vira caminho (mesma regra do
    `export_planilha.slug()`).
    """
    candidato = _candidato_do_token(token, db)
    slot = db.get(SlotDocumento, slot_id)
    if slot is None or slot.candidato_id != candidato.id:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    achado = next((t for t in _originais_do_slot(slot) if t[0] == indice), None)
    if achado is None:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado")
    _, nome, key = achado
    try:
        dados = storage.ler(key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="arquivo_nao_encontrado") from exc
    return _resposta_exibivel(nome, dados)


def _resposta_exibivel(nome: str, dados: bytes) -> Response:
    """Devolve o arquivo pronto para RENDERIZAR na tela.

    HEIC (foto de iPhone, caso comum aqui) e Word são convertidos ao servir; o
    arquivo guardado continua o original — a conversão é de exibição. Se a
    conversão falhar, o arquivo sai como veio, marcado para download: melhor
    baixar do que ficar sem ele.
    """
    from pathlib import Path

    ext = Path(nome.lower()).suffix
    ct = _CT_EXIBIVEL.get(ext)
    if ct is None:
        try:
            if ext in (".heic", ".heif", ".bmp"):
                dados, ct = _imagem_para_jpeg(dados), "image/jpeg"
                nome = f"{Path(nome).stem}.jpg"
            elif ext in (".doc", ".docx", ".odt", ".rtf"):
                from app.services.normalizacao import _word_para_pdf
                dados, ct = _word_para_pdf(ext, dados), "application/pdf"
                nome = f"{Path(nome).stem}.pdf"
        except Exception:
            log.warning("conversão de %s para exibição falhou; servindo como veio",
                        nome, exc_info=True)
            ct = None
    disp = "inline" if ct else "attachment"
    return Response(content=dados, media_type=ct or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{nome}"'})


def _imagem_para_jpeg(dados: bytes) -> bytes:
    """HEIC/BMP → JPEG. O `pillow_heif` já é registrado no import de
    `normalizacao` (é o que faz o Pillow abrir foto de iPhone)."""
    import io as _io

    from PIL import Image

    from app.services import normalizacao  # noqa: F401  (registra o HEIF opener)
    img = Image.open(_io.BytesIO(dados))
    img = img.convert("RGB")
    saida = _io.BytesIO()
    img.save(saida, format="JPEG", quality=90)
    return saida.getvalue()


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

    # Reabertura cirúrgica pós-aprovação: se o candidato já estava APROVADO e só
    # reenviou um documento que fora rejeitado, NÃO reabrimos o funil inteiro
    # (não vira `envio_concluido`) — a aprovação global fica intacta e o RH
    # reavalia apenas o slot reenviado. Só avisamos que houve reenvio.
    if candidato.status == StatusCandidato.aprovado:
        registrar(db, "documento_reenviado_pos_aprovacao", ator="candidato",
                  candidato_id=candidato.id)
        db.commit()
        from app.services.notificacoes import avisar_modelo
        avisar_modelo(
            db, "envio_concluido", "aviso_documento_reenviado",
            {"nome": candidato.nome_completo,
             "link": f"{base_url_publica(request)}/rh"})
        return {"status": candidato.status}

    candidato.status = StatusCandidato.envio_concluido
    registrar(db, "envio_concluido", ator="candidato", candidato_id=candidato.id)
    db.commit()

    # Quem recebe é configurável no painel (v1.82). Antes ia para `smtp_from`,
    # a caixa de LOGIN do e-mail — o RH recebia no e-mail pessoal sem poder
    # mudar. Sem configuração, cai no padrão de sempre.
    from app.services.notificacoes import avisar_modelo
    avisar_modelo(
        db, "envio_concluido", "aviso_envio_concluido",
        {"nome": candidato.nome_completo,
         "link": f"{base_url_publica(request)}/rh"})
    # Empurrão para quem compra uniforme (feedback 2026-07-28). Sai daqui, e não
    # do autosave da ficha, porque o wizard salva a cada 900ms — avisar a cada
    # tecla digitada faria o operacional parar de ler. O aviso NÃO leva os
    # tamanhos: a lista com nome, posto e medidas fica na tela Uniformes, para
    # não circular ficha de pessoal por e-mail (decisão do Bruno).
    from app.models.ficha import DadosProfissionaisBancarios
    _u = db.get(DadosProfissionaisBancarios, candidato.id)
    if _u and (_u.tamanho_calca or _u.tamanho_camisa or _u.tamanho_calcado):
        avisar_modelo(
            db, "uniforme_pendente", "aviso_uniforme",
            {"nome": candidato.nome_completo,
             "link": f"{base_url_publica(request)}/rh/uniformes"})
    return {"status": candidato.status}


@router.post("/c/{token}/reabrir-envio")
def reabrir_envio(token: str, db: Session = Depends(get_db)) -> dict:
    """Desfaz o 'CONCLUÍ MEU ENVIO' — mas só enquanto o RH não olhou nada.

    Feedback 2026-07-28: a pessoa clica em concluir, percebe na hora que mandou
    o documento errado e não tem como voltar; o checklist congela em
    `envio_concluido` e só o RH reabre. Quem tem menos recurso é justamente
    quem mais erra no envio e menos consegue pedir socorro.

    Guarda (condição do Vex): se QUALQUER slot já foi revisado (aprovado,
    rejeitado ou dispensado), a porta não reabre — trocar um documento que o RH
    já analisou faria a análise dele valer para um arquivo que não existe mais.
    Nesse caso o caminho continua sendo o RH reabrir o slot específico.
    """
    candidato = _candidato_do_token(token, db)
    if candidato.status != StatusCandidato.envio_concluido:
        raise HTTPException(status_code=409, detail="envio_nao_concluido")
    slots = db.scalars(select(SlotDocumento)
                       .where(SlotDocumento.candidato_id == candidato.id)).all()
    revisados = [s for s in slots if s.status in (StatusSlot.aprovado,
                                                  StatusSlot.rejeitado,
                                                  StatusSlot.dispensado)]
    if revisados:
        raise HTTPException(status_code=409, detail="rh_ja_revisou")
    candidato.status = StatusCandidato.docs_pendentes
    registrar(db, "envio_reaberto_pelo_candidato", ator="candidato",
              candidato_id=candidato.id)
    db.commit()
    return {"status": candidato.status}
