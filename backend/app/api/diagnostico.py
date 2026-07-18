"""Módulo de Diagnóstico do RH: investigar o que aconteceu com um colaborador
(linha do tempo, por que o dossiê não gerou) e os erros recentes do sistema —
sem console SQL/SSH (superfície de ataque). Só leitura.

Nasceu do incidente real (dossiê da Kátia que não gerava): a lição foi dar ao
RH uma ferramenta de investigação de verdade, dentro do painel."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.db import get_db
from app.models.candidato import Candidato
from app.models.documento import SlotDocumento
from app.models.evento import EventoAuditoria

router = APIRouter(tags=["diagnostico"], dependencies=[Depends(requer_rh)])

# Ações de auditoria que indicam falha — o "o que deu errado" do sistema.
ACOES_ERRO = ("dossie_falhou", "reset_senha_email_falhou")


def _traduzir_pendencia(p: str) -> str:
    tipo, _, valor = p.partition(":")
    nome = valor.replace("_", " ")
    if tipo == "ficha":
        return f"Ficha não assinada: {nome}"
    if tipo == "documento":
        return f"Documento obrigatório não aprovado: {nome}"
    return p


@router.get("/rh/candidatos/{candidato_id}/diagnostico")
def diagnostico_candidato(candidato_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Retrato completo para investigar um colaborador: dados-chave, por que o
    dossiê (não) gera, situação dos documentos e a linha do tempo de auditoria."""
    from app.api.assinaturas import NOMES_DOC, _docs_exigidos, _registro
    from app.api.ficha import pendencias_da_ficha
    from app.services.dossie import pendencias_do_dossie

    candidato = db.get(Candidato, candidato_id)
    if candidato is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")

    pend_dossie = [_traduzir_pendencia(p) for p in pendencias_do_dossie(db, candidato)]
    pend_ficha = pendencias_da_ficha(db, candidato)
    fichas = [
        {"documento": d.value, "titulo": NOMES_DOC[d],
         "assinado": _registro(db, candidato, d).assinado_em is not None}
        for d in _docs_exigidos(db, candidato)
    ]
    slots = db.scalars(select(SlotDocumento).where(
        SlotDocumento.candidato_id == candidato.id)).all()
    eventos = db.scalars(
        select(EventoAuditoria)
        .where(EventoAuditoria.candidato_id == candidato.id)
        .order_by(EventoAuditoria.criado_em.desc()).limit(200)
    ).all()

    return {
        "candidato": {
            "id": candidato.id, "nome": candidato.nome_completo,
            "status": candidato.status.value, "email": candidato.email,
            "celular_whatsapp": candidato.celular_whatsapp,
            "cargo_funcao": candidato.cargo_funcao,
            "posto_servico_id": candidato.posto_servico_id,
            "dossie_gerado_em": candidato.dossie_gerado_em,
        },
        "dossie": {
            "pode_gerar": not pend_dossie,
            "pendencias": pend_dossie,
        },
        "formulario_incompleto": pend_ficha,
        "fichas": fichas,
        "documentos": [
            {"tipo": s.tipo.value, "status": s.status.value,
             "obrigatorio": s.obrigatorio, "paginas": s.paginas}
            for s in slots
        ],
        "linha_do_tempo": [
            {"quando": e.criado_em, "acao": e.acao, "ator": e.ator,
             "ator_detalhe": e.ator_detalhe, "detalhe": e.detalhe}
            for e in eventos
        ],
    }


@router.get("/rh/diagnostico/erros")
def erros_recentes(limite: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    """Últimos erros registrados pelo sistema (falha de dossiê, de e-mail…),
    com o candidato afetado quando houver — o 'o que deu errado' do painel."""
    eventos = db.scalars(
        select(EventoAuditoria)
        .where(or_(*[EventoAuditoria.acao == a for a in ACOES_ERRO]))
        .order_by(EventoAuditoria.criado_em.desc()).limit(min(limite, 200))
    ).all()
    saida = []
    for e in eventos:
        nome = None
        if e.candidato_id:
            cand = db.get(Candidato, e.candidato_id)
            nome = cand.nome_completo if cand else None
        saida.append({"quando": e.criado_em, "acao": e.acao, "ator": e.ator,
                      "candidato_id": e.candidato_id, "candidato_nome": nome,
                      "detalhe": e.detalhe})
    return saida
