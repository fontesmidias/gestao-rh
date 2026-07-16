"""Poderes manuais do RH (fase 2 do feedback de campo, 2026-07-15).

Linhas vermelhas do projeto (mesa-redonda de segurança):
1. Nada some sem hash na auditoria.
2. Toda ação manual do RH sai assinada com o usuário e o motivo.
3. O clique de assinar é SEMPRE do candidato — o RH prepara, nunca assina.

Daqui saem: upload manual de documento recebido fora do sistema (WhatsApp,
presencial), reabertura de status de slot, e edição de dados da ficha com
invalidação granular das assinaturas afetadas (só as fichas onde o dado
aparece voltam para o candidato assinar — a operação não para).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica
from app.core.db import get_db
from app.models.assinatura import Assinatura, DocumentoAssinavel
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import SlotDocumento, StatusSlot
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.email import enviar_email, html_moderno
from app.services.magic_link import emitir_link
from app.services.normalizacao import ArquivoInvalido, normalizar_para_pdf

router = APIRouter(tags=["rh-manual"], dependencies=[Depends(requer_rh)])

_TODOS = list(DocumentoAssinavel)

# Em qual documento assinável cada seção da ficha aparece. Mapa CONSERVADOR:
# na dúvida, invalida — melhor o candidato re-assinar do que um PDF assinado
# divergir dos dados reais.
DOCS_POR_SECAO: dict[str, list[DocumentoAssinavel]] = {
    "pessoais": _TODOS,
    "documentos": _TODOS,
    "endereco": [DocumentoAssinavel.ficha_cadastro, DocumentoAssinavel.termo_vt],
    "trabalho-banco": [DocumentoAssinavel.ficha_cadastro],
    "vt-emergencia": [DocumentoAssinavel.termo_vt, DocumentoAssinavel.ficha_emergencia],
}


def invalidar_assinaturas_afetadas(db: Session, candidato: Candidato, secao: str,
                                   ator_detalhe: str, campos: list[str]) -> list[str]:
    """Invalida (nunca deleta) as assinaturas concluídas dos documentos onde a
    seção editada aparece, e cria um novo registro pendente de cada um. Devolve
    os nomes dos documentos que voltaram para assinatura."""
    invalidados: list[str] = []
    for doc in DOCS_POR_SECAO.get(secao, []):
        assinatura = db.scalar(
            select(Assinatura).where(
                Assinatura.candidato_id == candidato.id, Assinatura.documento == doc,
                Assinatura.assinado_em.isnot(None), Assinatura.invalidada_em.is_(None),
            )
        )
        if assinatura is None:
            continue
        assinatura.invalidada_em = datetime.now(timezone.utc)
        assinatura.invalidada_motivo = (
            f"Dados da seção '{secao}' atualizados por {ator_detalhe} "
            f"(campos: {', '.join(campos)})"
        )[:300]
        registrar(db, "assinatura_invalidada", ator="rh", ator_detalhe=ator_detalhe,
                  candidato_id=candidato.id,
                  detalhe={"documento": doc.value, "hash": assinatura.hash_sha256,
                           "secao": secao, "campos": campos})
        db.add(Assinatura(candidato_id=candidato.id, documento=doc))
        invalidados.append(doc.value)
    return invalidados


class EdicaoSecaoIn(BaseModel):
    dados: dict
    motivo: str


@router.get("/rh/candidatos/{candidato_id}/ficha")
def ficha_do_candidato(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    from app.api.ficha import montar_ficha
    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    return montar_ficha(db, candidato)


@router.put("/rh/candidatos/{candidato_id}/ficha/{secao}")
def editar_secao(
    candidato_id: uuid.UUID,
    secao: str,
    payload: EdicaoSecaoIn,
    request: Request,
    db: Session = Depends(get_db),
    rh: UsuarioRH = Depends(requer_rh),
) -> dict:
    """O RH completa/corrige dados da ficha. Validação idêntica à do candidato
    (mesmos schemas); auditoria com antes → depois; e se algum documento já
    assinado exibe esses dados, a assinatura é invalidada e o candidato é
    avisado para assinar a versão atualizada — quem assina é sempre ele."""
    from app.api import ficha as ficha_api

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if candidato.status == StatusCandidato.expurgado:
        raise HTTPException(status_code=409, detail="candidato_expurgado")
    if not payload.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")

    schemas = {
        "pessoais": (ficha_api.SecaoPessoais, ficha_api.DadosPessoais),
        "endereco": (ficha_api.SecaoEndereco, ficha_api.Endereco),
        "documentos": (ficha_api.SecaoDocumentos, ficha_api.DocumentosIdentificacao),
        "trabalho-banco": (ficha_api.SecaoTrabalhoBanco,
                           ficha_api.DadosProfissionaisBancarios),
        "vt-emergencia": (ficha_api.SecaoVtEmergencia, None),
    }
    if secao not in schemas:
        raise HTTPException(status_code=404, detail="secao_desconhecida")
    schema, modelo = schemas[secao]
    dados = schema(**payload.dados).model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=422, detail="nada_para_alterar")

    # Antes → depois, campo a campo, para a auditoria.
    mudancas: dict[str, tuple] = {}

    def _aplicar(obj, campo: str, valor) -> None:
        mudancas[campo] = (getattr(obj, campo, None), valor)
        setattr(obj, campo, valor)

    if secao == "pessoais":
        for campo in ("nome_completo", "email", "celular_whatsapp"):
            if campo in dados:
                _aplicar(candidato, campo, dados.pop(campo))
    if secao == "vt-emergencia":
        from app.models.ficha import FichaEmergencia, ValeTransporte
        vt = {k.removeprefix("vt_"): v for k, v in dados.items() if k.startswith("vt_")}
        emergencia = {k: v for k, v in dados.items() if not k.startswith("vt_")}
        vt.pop("ciencia_cartao_go", None)  # ciência é ato do candidato, não do RH
        for cls, valores in ((ValeTransporte, vt), (FichaEmergencia, emergencia)):
            if not valores:
                continue
            obj = db.get(cls, candidato.id) or cls(candidato_id=candidato.id)
            db.add(obj)
            for campo, valor in valores.items():
                _aplicar(obj, campo, valor)
    elif dados:
        obj = db.get(modelo, candidato.id) or modelo(candidato_id=candidato.id)
        db.add(obj)
        for campo, valor in dados.items():
            _aplicar(obj, campo, valor)

    if not mudancas:
        raise HTTPException(status_code=422, detail="nada_para_alterar")
    campos = sorted(mudancas.keys())
    registrar(db, "ficha_editada_rh", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"secao": secao, "motivo": payload.motivo.strip(),
                       "antes": {k: _txt(v[0]) for k, v in mudancas.items()},
                       "depois": {k: _txt(v[1]) for k, v in mudancas.items()}})

    invalidados = invalidar_assinaturas_afetadas(db, candidato, secao, rh.email, campos)
    db.commit()

    email_enviado = False
    if invalidados and candidato.email:
        link = emitir_link(db, candidato, base_url_publica(request))
        db.commit()
        nomes = _nomes_docs(invalidados)
        email_enviado = enviar_email(
            candidato.email,
            "Green House — documentos atualizados aguardam sua assinatura",
            f"Prezado(a) {candidato.nome_completo},\n\n"
            f"O RH atualizou informações da sua ficha ({payload.motivo.strip()}). "
            "Com isso, os documentos abaixo foram regenerados e precisam ser "
            "assinados novamente:\n"
            + "\n".join(f"  - {n}" for n in nomes)
            + f"\n\nAcesse: {link}\n\nA assinatura leva menos de um minuto — faça "
            "HOJE para não atrasar a sua contratação.\n\nAtenciosamente,\nRH — Green House\n",
            html_moderno(
                "Documentos aguardam nova assinatura",
                [
                    f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                    f"O RH atualizou informações da sua ficha "
                    f"(<strong>{payload.motivo.strip()}</strong>). Os documentos abaixo "
                    "foram regenerados e precisam ser assinados novamente:"
                    + "<ul style='margin:8px 0 0 18px;color:#3a4152'>"
                    + "".join(f"<li>{n}</li>" for n in nomes) + "</ul>",
                    f"<a href='{link}'>Toque aqui para assinar</a> — leva menos de um "
                    "minuto. Faça <strong>hoje</strong> para não atrasar a sua contratação.",
                ],
            ),
        )

    return {"secao": secao, "campos_alterados": campos,
            "assinaturas_invalidadas": invalidados, "email_enviado": email_enviado}


def _txt(v) -> str | None:
    if v is None:
        return None
    return str(v.value) if hasattr(v, "value") else str(v)


def _nomes_docs(valores: list[str]) -> list[str]:
    from app.api.assinaturas import NOMES_DOC
    return [NOMES_DOC[DocumentoAssinavel(v)] for v in valores]


@router.post("/rh/slots/{slot_id}/arquivo")
def inserir_arquivo_rh(
    slot_id: uuid.UUID,
    arquivo: UploadFile,
    origem: str = Form("whatsapp"),
    db: Session = Depends(get_db),
    rh: UsuarioRH = Depends(requer_rh),
) -> dict:
    """Documento que chegou fora do sistema (WhatsApp, e-mail, presencial):
    o RH insere no slot com etiqueta de origem — visível no painel e na
    auditoria. Passa pelas mesmas validações do envio do candidato."""
    from app.api.documentos import _gravar_no_slot, _slot_out

    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    candidato = db.get(Candidato, slot.candidato_id)

    dados = arquivo.file.read()
    try:
        pdf, paginas = normalizar_para_pdf(arquivo.filename or "arquivo", dados,
                                           rotulo=slot.tipo.value)
    except ArquivoInvalido as exc:
        raise HTTPException(status_code=422, detail=exc.codigo) from exc

    _gravar_no_slot(db, candidato, slot, arquivo.filename, arquivo.content_type,
                    dados, pdf, paginas)
    slot.origem_envio = "rh"
    slot.origem_envio_obs = origem.strip()[:120] or "whatsapp"
    registrar(db, "documento_inserido_rh", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"tipo": slot.tipo.value, "origem": slot.origem_envio_obs,
                       "paginas": paginas})
    db.commit()
    return _slot_out(slot) | {"origem_envio": slot.origem_envio,
                              "origem_envio_obs": slot.origem_envio_obs}


@router.post("/rh/candidatos/{candidato_id}/notificar")
def notificar_pendencias(candidato_id: uuid.UUID, request: Request,
                         db: Session = Depends(get_db),
                         rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Cobra o candidato por e-mail com o retrato exato do que falta: ficha
    incompleta, fichas aguardando assinatura e/ou documentos pendentes — com
    um link novo. Nasceu do incidente real: e-mail cadastrado depois, e a
    pessoa nunca soube que havia fichas para preencher e assinar."""
    from app.api.assinaturas import NOMES_DOC, _docs_exigidos, _registro
    from app.api.ficha import pendencias_da_ficha

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if not candidato.email:
        raise HTTPException(status_code=422, detail="candidato_sem_email")

    pend_ficha = pendencias_da_ficha(db, candidato)
    fichas_pendentes = [NOMES_DOC[d] for d in _docs_exigidos(db, candidato)
                        if _registro(db, candidato, d).assinado_em is None]
    slots = db.scalars(select(SlotDocumento).where(
        SlotDocumento.candidato_id == candidato.id)).all()
    docs_pendentes = [s.tipo.value.replace("_", " ")
                      for s in slots if s.obrigatorio and s.status in
                      (StatusSlot.pendente, StatusSlot.rejeitado)]

    itens: list[str] = []
    if pend_ficha:
        itens.append(f"Completar o formulário da admissão ({len(pend_ficha)} "
                     "campo(s) obrigatório(s) em aberto)")
    if fichas_pendentes:
        itens.append("Assinar eletronicamente: " + "; ".join(fichas_pendentes))
    if docs_pendentes:
        itens.append("Enviar os documentos: " + "; ".join(docs_pendentes))
    if not itens:
        raise HTTPException(status_code=409, detail="sem_pendencias")

    link = emitir_link(db, candidato, base_url_publica(request))
    registrar(db, "candidato_notificado", ator="rh", ator_detalhe=rh.email,
              candidato_id=candidato.id,
              detalhe={"pendencias_ficha": len(pend_ficha),
                       "fichas_para_assinar": len(fichas_pendentes),
                       "documentos_pendentes": len(docs_pendentes)})
    db.commit()

    lista_txt = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(itens))
    lista_html = "".join(f"<li>{t}</li>" for t in itens)
    enviado = enviar_email(
        candidato.email,
        "Green House — sua admissão tem pendências que dependem de você",
        f"Prezado(a) {candidato.nome_completo},\n\n"
        "Sua admissão está parada aguardando as providências abaixo:\n\n"
        f"{lista_txt}\n\n"
        f"Acesse: {link}\n\n"
        "Resolva HOJE — sua contratação somente será efetivada após a "
        "conclusão de todas as etapas.\n\nAtenciosamente,\nRH — Green House\n",
        html_moderno(
            "Sua admissão tem pendências",
            [
                f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                "Sua admissão está parada aguardando as providências abaixo:"
                f"<ol style='margin:8px 0 0 18px;color:#3a4152'>{lista_html}</ol>",
                f"<a href='{link}'>Toque aqui para continuar de onde parou</a>. "
                "Resolva <strong>hoje</strong> — sua contratação somente será "
                "efetivada após a conclusão de todas as etapas.",
            ],
        ),
    )
    return {"email_enviado": enviado, "itens": itens, "link_magico": link}


class ReabrirIn(BaseModel):
    motivo: str


@router.post("/rh/slots/{slot_id}/reabrir")
def reabrir_slot(slot_id: uuid.UUID, payload: ReabrirIn,
                 db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Desfaz uma aprovação/dispensa/rejeição feita por engano. Com arquivo,
    o slot volta para 'em análise'; sem arquivo, volta a 'pendente'."""
    slot = db.get(SlotDocumento, slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot_nao_encontrado")
    if not payload.motivo.strip():
        raise HTTPException(status_code=422, detail="motivo_obrigatorio")
    if slot.status in (StatusSlot.pendente, StatusSlot.enviado):
        raise HTTPException(status_code=409, detail="slot_ja_esta_aberto")

    anterior = slot.status.value
    slot.status = StatusSlot.enviado if slot.arquivo_pdf_key else StatusSlot.pendente
    slot.motivo_rejeicao = None
    slot.motivo_rejeicao_obs = None
    slot.revisado_em = datetime.now(timezone.utc)
    slot.revisado_por = rh.id
    registrar(db, "slot_reaberto", ator="rh", ator_detalhe=rh.email,
              candidato_id=slot.candidato_id,
              detalhe={"tipo": slot.tipo.value, "de": anterior,
                       "para": slot.status.value, "motivo": payload.motivo.strip()})
    db.commit()
    return {"status": slot.status}
