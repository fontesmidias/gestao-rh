"""Painel do RH: lista de candidatos, revisão de documentos e dossiê."""

import unicodedata
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, get_settings
from app.core.db import get_db
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import MotivoRejeicao, SlotDocumento, StatusSlot
from app.models.usuario_rh import UsuarioRH
from app.services import storage
from app.services.auditoria import registrar
from app.services.dossie import DossieIncompleto, gerar_dossie
from app.services.email import enviar_email, html_moderno

router = APIRouter(tags=["revisao-rh"], dependencies=[Depends(requer_rh)])


def _candidatos_admissao(db: Session, status: str | None, busca: str | None,
                         posto_id: uuid.UUID | None) -> list[Candidato]:
    """Filtra a lista de Admissões. Com o uso, serão muitos admitidos — daí os
    filtros (feedback 2026-07-19)."""
    q = select(Candidato).order_by(Candidato.criado_em.desc())
    if status:
        try:
            q = q.where(Candidato.status == StatusCandidato(status))
        except ValueError:
            pass
    if posto_id:
        q = q.where(Candidato.posto_servico_id == posto_id)
    candidatos = db.scalars(q).all()
    if busca:
        from app.models.ficha import DocumentosIdentificacao
        termo = busca.strip().lower()
        digitos = "".join(c for c in termo if c.isdigit())
        cpfs = {}
        if digitos:
            for d in db.scalars(select(DocumentosIdentificacao)).all():
                cpfs[d.candidato_id] = d.cpf or ""
        candidatos = [c for c in candidatos
                      if termo in (c.nome_completo or "").lower()
                      or termo in (c.email or "").lower()
                      or (digitos and (digitos in "".join(x for x in (c.cpf or "") if x.isdigit())
                                       or digitos in cpfs.get(c.id, "")))]
    return candidatos


@router.get("/rh/candidatos")
def listar_candidatos(status: str | None = None, busca: str | None = None,
                      posto_id: uuid.UUID | None = None,
                      db: Session = Depends(get_db)) -> list[dict]:
    candidatos = _candidatos_admissao(db, status, busca, posto_id)
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


@router.get("/rh/candidatos-exportar")
def exportar_admissoes(status: str | None = None, busca: str | None = None,
                       posto_id: uuid.UUID | None = None,
                       db: Session = Depends(get_db),
                       _rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Planilha das admissões (mesmos filtros da tela), reusando o service de
    export compartilhado."""
    from datetime import datetime, timezone

    from app.services.export_planilha import linha_completa, montar_workbook
    candidatos = _candidatos_admissao(db, status, busca, posto_id)
    conteudo = montar_workbook([linha_completa(db, c) for c in candidatos])
    registrar(db, "admissoes_exportadas", ator="rh", ator_detalhe=_rh.email,
              detalhe={"linhas": len(candidatos), "status": status or "todos"})
    db.commit()
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="admissoes-{agora}.xlsx"'})


# O export EM MASSA para o Tirvu vive em `colaboradores.py`: só se manda para
# lá quem já virou colaborador (efetivado) — quem ainda está em admissão não
# tem vínculo para criar no Tirvu. Aqui fica apenas o export individual, usado
# pelo botão na ficha da pessoa.


@router.get("/rh/candidatos/{candidato_id}/exportar-tirvu")
def exportar_tirvu_individual(candidato_id: uuid.UUID,
                              db: Session = Depends(get_db),
                              _rh: UsuarioRH = Depends(requer_rh)) -> Response:
    """Planilha do Tirvu com UMA admissão (botão na ficha do aprovado)."""
    from app.services.export_planilha import slug
    from app.services.export_tirvu import linha_tirvu, montar_workbook_tirvu

    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(404, "Candidato não encontrado")
    # planilha CRUA no formato exato do Tirvu (aba Plan1, sem filtro/cor/freeze);
    # gerar_matricula=True grava a matrícula automática se faltar (commit abaixo).
    conteudo = montar_workbook_tirvu([linha_tirvu(db, cand, gerar_matricula=True)])
    registrar(db, "tirvu_exportado", ator="rh", ator_detalhe=_rh.email,
              detalhe={"linhas": 1, "candidato": str(cand.id)})
    db.commit()
    nome = slug(cand.nome_completo, fallback="admissao")
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="importacao-tirvu-{nome}.xlsx"'})


@router.get("/rh/metricas")
def metricas(db: Session = Depends(get_db)) -> dict:
    """Números do painel: funil de candidatos, fila de revisão e tempo médio."""
    candidatos = db.scalars(select(Candidato)).all()
    slots = db.scalars(select(SlotDocumento)).all()

    por_status: dict[str, int] = {}
    for c in candidatos:
        por_status[c.status.value] = por_status.get(c.status.value, 0) + 1

    aguardando_revisao = sum(1 for s in slots if s.status == StatusSlot.enviado)
    rejeitados_abertos = sum(1 for s in slots if s.status == StatusSlot.rejeitado)

    concluidos = [c for c in candidatos if c.dossie_gerado_em is not None]
    tempo_medio_min = None
    if concluidos:
        total = sum((c.dossie_gerado_em - c.criado_em).total_seconds() for c in concluidos)
        # Em minutos (pedido do RH): a média real é curta demais para "dias".
        tempo_medio_min = round(total / len(concluidos) / 60)

    return {
        "total_candidatos": len(candidatos),
        "por_status": por_status,
        "documentos_aguardando_revisao": aguardando_revisao,
        "documentos_rejeitados_em_aberto": rejeitados_abertos,
        "dossies_gerados": len(concluidos),
        "tempo_medio_minutos_convite_ao_dossie": tempo_medio_min,
    }


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
    from app.api.assinaturas import NOMES_DOC, _docs_exigidos, chave_doc, titulo_doc
    from app.api.ficha import pendencias_da_ficha
    from app.models.assinatura import Assinatura
    assinaturas = db.scalars(
        select(Assinatura).where(Assinatura.candidato_id == cand.id,
                                 Assinatura.invalidada_em.is_(None))).all()
    por_doc = {a.documento: a for a in assinaturas if a.documento}
    fichas = [
        {"documento": doc, "titulo": NOMES_DOC[doc],
         "assinado": doc in por_doc and por_doc[doc].assinado_em is not None,
         "assinado_em": por_doc[doc].assinado_em if doc in por_doc else None}
        for doc in _docs_exigidos(db, cand)
    ] + [
        # documentos de modelo enviados para assinatura deste colaborador
        {"documento": chave_doc(a), "titulo": titulo_doc(a),
         "assinado": a.assinado_em is not None, "assinado_em": a.assinado_em}
        for a in assinaturas if a.modelo_id is not None
    ]
    return {
        "id": cand.id,
        "nome_completo": cand.nome_completo,
        "email": cand.email,
        "celular_whatsapp": cand.celular_whatsapp,
        "status": cand.status,
        "situacao": cand.situacao,  # None se ainda em admissão; ativo/desligado se colaborador
        "data_admissao": cand.data_admissao,
        "data_desligamento": cand.data_desligamento,
        "dossie_gerado_em": cand.dossie_gerado_em,
        "posto_servico_id": cand.posto_servico_id,
        "cargo_funcao": cand.cargo_funcao,
        "salario_base": cand.salario_base,
        "adicionais": cand.adicionais or [],
        "empresa_id": cand.empresa_id,
        "jornada_id": cand.jornada_id,
        "registra_ponto": cand.registra_ponto,
        "assinaturas": [
            {"documento": chave_doc(a), "titulo": titulo_doc(a),
             "assinado_em": a.assinado_em}
            for a in assinaturas
        ],
        # Visão que faltava no incidente real: fichas sem dados/sem assinatura
        # eram invisíveis para o RH — agora cada documento exigido aparece com
        # o seu estado, e a ficha incompleta grita.
        "fichas": fichas,
        "pendencias_ficha": pendencias_da_ficha(db, cand),
        "slots": [
            {
                "id": s.id,
                "tipo": s.tipo,
                "dependente_id": s.dependente_id,
                "obrigatorio": s.obrigatorio,
                "status": s.status,
                "motivo_rejeicao": s.motivo_rejeicao,
                "paginas": s.paginas,
                "origem_envio": s.origem_envio,
                "origem_envio_obs": s.origem_envio_obs,
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


# As rotas de lote precisam vir ANTES das rotas /rh/slots/{slot_id}/...:
# o FastAPI casa na ordem de declaração e "lote" seria capturado pelo
# path param {slot_id}, falhando a validação de UUID com 422.


class LoteAprovarIn(BaseModel):
    slot_ids: list[uuid.UUID]


@router.post("/rh/slots/lote/aprovar")
def aprovar_lote(payload: LoteAprovarIn, db: Session = Depends(get_db),
                 rh: UsuarioRH = Depends(requer_rh)) -> dict:
    aprovados = 0
    for slot_id in payload.slot_ids:
        slot = db.get(SlotDocumento, slot_id)
        if slot is None or slot.status != StatusSlot.enviado:
            continue
        slot.status = StatusSlot.aprovado
        slot.revisado_em = datetime.now(timezone.utc)
        slot.revisado_por = rh.id
        registrar(db, "documento_aprovado", ator="rh", ator_detalhe=rh.email,
                  candidato_id=slot.candidato_id, detalhe={"tipo": slot.tipo.value, "lote": True})
        aprovados += 1
    db.commit()
    return {"aprovados": aprovados}


class LoteRejeitarIn(BaseModel):
    slot_ids: list[uuid.UUID]
    motivo: MotivoRejeicao
    observacao: str | None = None


@router.post("/rh/slots/lote/rejeitar")
def rejeitar_lote(payload: LoteRejeitarIn, db: Session = Depends(get_db),
                  rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Rejeita vários documentos; o candidato recebe UM e-mail listando tudo."""
    rejeitados_por_candidato: dict[uuid.UUID, list[SlotDocumento]] = {}
    for slot_id in payload.slot_ids:
        slot = db.get(SlotDocumento, slot_id)
        if slot is None or slot.status != StatusSlot.enviado:
            continue
        slot.status = StatusSlot.rejeitado
        slot.motivo_rejeicao = payload.motivo
        slot.motivo_rejeicao_obs = payload.observacao
        slot.revisado_em = datetime.now(timezone.utc)
        slot.revisado_por = rh.id
        from app.api.documentos import expurgar_arquivos_do_slot
        expurgar_arquivos_do_slot(db, slot, evento="documento_rejeitado_expurgado",
                                  ator="rh", ator_detalhe=rh.email)
        registrar(db, "documento_rejeitado", ator="rh", ator_detalhe=rh.email,
                  candidato_id=slot.candidato_id,
                  detalhe={"tipo": slot.tipo.value, "motivo": payload.motivo.value, "lote": True})
        rejeitados_por_candidato.setdefault(slot.candidato_id, []).append(slot)

    total = 0
    for candidato_id, slots in rejeitados_por_candidato.items():
        candidato = db.get(Candidato, candidato_id)
        if candidato.status == StatusCandidato.envio_concluido:
            candidato.status = StatusCandidato.docs_pendentes
        total += len(slots)
        lista = "\n".join(f"  - {s.tipo.value.replace('_', ' ')}" for s in slots)
        enviar_email(
            candidato.email,
            "Green House — documentos precisam ser reenviados",
            f"Prezado(a) {candidato.nome_completo},\n\n"
            f"Os documentos abaixo precisam ser enviados novamente "
            f"({_MOTIVO_LEGIVEL[payload.motivo]}"
            + (f" — {payload.observacao}" if payload.observacao else "") + "):\n"
            f"{lista}\n\n"
            "Acesse o mesmo link da sua admissão e reenvie-os HOJE. Sua contratação fica "
            "parada até esse reenvio.\n\nAtenciosamente,\nRH — Green House\n",
            html_moderno(
                "Documentos precisam ser reenviados",
                [
                    f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                    f"Os documentos abaixo precisam ser enviados novamente "
                    f"(<strong>{_MOTIVO_LEGIVEL[payload.motivo]}</strong>"
                    + (f" — {payload.observacao}" if payload.observacao else "") + "):"
                    + "<ul style='margin:8px 0 0 18px;color:#3a4152'>"
                    + "".join(f"<li>{s.tipo.value.replace('_', ' ')}</li>" for s in slots)
                    + "</ul>",
                    "Acesse o mesmo link da sua admissão e <strong>reenvie-os HOJE</strong>. "
                    "Sua contratação fica parada até esse reenvio.",
                ],
            ),
        )
    db.commit()
    return {"rejeitados": total}


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
    # Arquivo reprovado sai do storage na hora (minimização de dados) — o hash
    # fica na auditoria e o slot abre para o candidato reenviar.
    from app.api.documentos import expurgar_arquivos_do_slot
    expurgar_arquivos_do_slot(db, slot, evento="documento_rejeitado_expurgado",
                              ator="rh", ator_detalhe=rh.email)

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
        + ".\n\nAcesse o mesmo link da sua admissão e reenvie esse documento HOJE. "
          "Sua contratação fica parada até esse reenvio — não deixe para depois.\n",
        html_moderno(
            "Um documento precisa ser reenviado",
            [
                f"Prezado(a) <strong>{candidato.nome_completo}</strong>,",
                f"Um dos seus documentos precisa ser enviado novamente: "
                f"<strong>{_MOTIVO_LEGIVEL[payload.motivo]}</strong>"
                + (f" ({payload.observacao})" if payload.observacao else "") + ".",
                "Acesse o mesmo link da sua admissão e <strong>reenvie esse documento "
                "HOJE</strong>. Sua contratação fica parada até esse reenvio.",
            ],
        ),
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
def gerar_dossie_endpoint(candidato_id: uuid.UUID, request: Request, forcar: bool = False,
                          db: Session = Depends(get_db)) -> dict:
    """forcar=true gera o dossiê parcial mesmo com pendências (decisão do RH,
    registrada em auditoria); o status só vira 'aprovado' quando completo."""
    from app.services.idempotencia import trava
    cand = db.get(Candidato, candidato_id)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    # trava de idempotência: dois cliques em "Gerar dossiê" não geram dois PDFs
    # nem dois e-mails; a 2ª chamada concorrente recebe 409 ja_em_processamento.
    with trava(f"dossie:{cand.id}"):
        try:
            gerar_dossie(db, cand, ignorar_pendencias=forcar)
        except DossieIncompleto as exc:
            raise HTTPException(status_code=422, detail={"pendencias": exc.pendencias}) from exc
        except Exception as exc:
            # Erro REAL (arquivo faltando no storage, PDF corrompido…): registra com
            # detalhe e devolve mensagem legível. Antes virava um 500 genérico que o
            # painel exibia como "sem pendências" — o RH achava que estava tudo certo.
            import logging
            logging.getLogger(__name__).exception("Falha ao montar o dossiê de %s", cand.id)
            registrar(db, "dossie_falhou", ator="rh", candidato_id=cand.id,
                      detalhe={"erro": f"{type(exc).__name__}: {exc}"[:300]})
            db.commit()
            raise HTTPException(status_code=422,
                                detail=f"erro_ao_montar_dossie: {type(exc).__name__}") from exc
        if not forcar:
            cand.status = StatusCandidato.aprovado
        registrar(db, "dossie_gerado", ator="rh", candidato_id=cand.id,
                  detalhe={"parcial": forcar})
        db.commit()

        # Aviso interno "Dossiê pronto": vai para o e-mail configurado no painel
        # (Configurações → E-mail de avisos internos), com fallback ao remetente.
        from app.services.config_dinamica import ler_config
        destino = (ler_config(db, ("email_avisos_internos",)).get("email_avisos_internos")
                   or get_settings().smtp_from)
        if destino:
            enviar_email(
                destino,
                f"📄 Dossiê de admissão pronto: {cand.nome_completo}",
                f"O dossiê completo de {cand.nome_completo} foi gerado.\n"
                f"Baixe no painel: {base_url_publica(request)}/rh\n",
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
