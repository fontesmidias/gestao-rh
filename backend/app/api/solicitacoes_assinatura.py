"""Multi-signatário — API do roteiro de assinatura em ordem de papéis.

Fase RH: o RH monta o roteiro (quem assina, em que papel/ordem) e dispara;
signatários que são USUÁRIOS do RH assinam logados (prova = senha revalidada);
o CANDIDATO assina pelo fluxo de link mágico de sempre, e um hook promove a
etapa dele. Signatário EXTERNO fica em `solicitacoes_externo.py` (fase 4).

Correções incorporadas: C1 (via dedicada do candidato marcada), C3 (avanço
serializado), C4 (RH só assina a própria etapa + lockout), M5 (snapshot do
assinante), M6 (recusa != cancelamento), M7 (e-mail fora da transação).
"""

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_rh import requer_rh
from app.core.config import base_url_publica, ip_do_cliente
from app.core.db import get_db
from app.core.security import verificar_senha
from app.models.assinatura import Assinatura
from app.models.candidato import Candidato
from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                               SolicitacaoAssinatura,
                                               StatusSolicitacao, TipoSignatario)
from app.models.usuario_rh import UsuarioRH
from app.services.auditoria import registrar
from app.services.limite import exigir
from app.services.roteiro_assinatura import avancar_solicitacao

router = APIRouter(tags=["solicitacoes-assinatura"])

MAX_TENTATIVAS_SENHA = 5


# ---------------------------------------------------------------------------
# Montagem do roteiro (RH)
# ---------------------------------------------------------------------------


class EtapaIn(BaseModel):
    papel: str
    ordem: int
    tipo: TipoSignatario
    usuario_rh_id: uuid.UUID | None = None
    externo_nome: str | None = None
    externo_email: str | None = None
    externo_cpf: str | None = None


class NovaSolicitacaoIn(BaseModel):
    documento: str | None = None
    modelo_id: uuid.UUID | None = None
    expira_em: datetime | None = None
    etapas: list[EtapaIn]


def _dump_etapa(e: EtapaAssinatura) -> dict:
    return {
        "id": e.id, "papel": e.papel, "ordem": e.ordem,
        "tipo": e.tipo_signatario,
        "quem": (e.externo_nome or e.assinante_nome
                 or (str(e.usuario_rh_id) if e.usuario_rh_id else "candidato")),
        "assinado_em": e.assinado_em, "recusada_em": e.recusada_em,
        "recusada_motivo": e.recusada_motivo,
    }


def _dump_sol(db: Session, sol: SolicitacaoAssinatura) -> dict:
    etapas = db.scalars(select(EtapaAssinatura)
                        .where(EtapaAssinatura.solicitacao_id == sol.id)
                        .order_by(EtapaAssinatura.ordem)).all()
    return {
        "id": sol.id, "candidato_id": sol.candidato_id,
        "titulo": sol.titulo_doc or sol.documento, "status": sol.status,
        "etapa_atual_ordem": sol.etapa_atual_ordem,
        "criado_em": sol.criado_em, "concluida": sol.status == StatusSolicitacao.concluida,
        "pdf_final": bool(sol.pdf_final_key),
        "etapas": [_dump_etapa(e) for e in etapas],
    }


@router.post("/rh/candidatos/{cid}/solicitacoes-assinatura", status_code=201,
             dependencies=[Depends(requer_rh)])
def montar_roteiro(cid: uuid.UUID, payload: NovaSolicitacaoIn, request: Request,
                   db: Session = Depends(get_db),
                   rh: UsuarioRH = Depends(requer_rh)) -> dict:
    cand = db.get(Candidato, cid)
    if cand is None:
        raise HTTPException(status_code=404, detail="candidato_nao_encontrado")
    if bool(payload.documento) == bool(payload.modelo_id):
        raise HTTPException(status_code=422, detail="informe_documento_ou_modelo")
    # roteiro vazio + modelo com roteiro-padrão só de CANDIDATO → materializa
    # direto (essas etapas não precisam de pessoa). Etapas de RH/externo do
    # padrão exigem escolher a pessoa, então a UI pré-carrega o padrão e o RH
    # completa — não materializamos etapa sem pessoa (correção M9).
    etapas_in = list(payload.etapas)
    if not etapas_in and payload.modelo_id:
        from app.models.solicitacao_assinatura import ModeloEtapaPadrao
        padrao = db.scalars(select(ModeloEtapaPadrao)
                            .where(ModeloEtapaPadrao.modelo_id == payload.modelo_id)
                            .order_by(ModeloEtapaPadrao.ordem)).all()
        etapas_in = [EtapaIn(papel=p.papel, ordem=p.ordem, tipo=p.tipo_sugerido)
                     for p in padrao if p.tipo_sugerido == TipoSignatario.candidato]
    if not etapas_in:
        raise HTTPException(status_code=422, detail="roteiro_sem_etapas")

    titulo, corpo = _titulo_corpo(db, payload)
    sol = SolicitacaoAssinatura(
        candidato_id=cand.id, documento=payload.documento, modelo_id=payload.modelo_id,
        titulo_doc=titulo, corpo_doc=corpo, expira_em=payload.expira_em,
        criada_por=rh.email, status=StatusSolicitacao.rascunho)
    db.add(sol)
    db.flush()

    for e in etapas_in:
        etapa = EtapaAssinatura(id=uuid.uuid4(), solicitacao_id=sol.id,
                                papel=e.papel.strip()[:60],
                                ordem=e.ordem, tipo_signatario=e.tipo)
        if e.tipo == TipoSignatario.usuario_rh:
            if not e.usuario_rh_id or db.get(UsuarioRH, e.usuario_rh_id) is None:
                raise HTTPException(status_code=422, detail="usuario_rh_invalido")
            etapa.usuario_rh_id = e.usuario_rh_id
        elif e.tipo == TipoSignatario.externo:
            if not (e.externo_nome and e.externo_email):
                raise HTTPException(status_code=422, detail="externo_precisa_nome_email")
            etapa.externo_nome = e.externo_nome.strip()[:120]
            etapa.externo_email = e.externo_email.strip()[:180]
            etapa.externo_cpf = "".join(c for c in (e.externo_cpf or "") if c.isdigit())[:11] or None
        elif e.tipo == TipoSignatario.candidato:
            # via DEDICADA do candidato (correção C1): Assinatura marcada, nunca
            # a de fluxo livre. Fica pendente até ele assinar pelo link.
            a = Assinatura(candidato_id=cand.id, documento=payload.documento,
                           modelo_id=payload.modelo_id, titulo_doc=titulo, corpo_doc=corpo,
                           papel=e.papel.strip()[:60], solicitacao_etapa_id=str(etapa.id))
            db.add(a)
            db.flush()
            etapa.assinatura_id = a.id
        db.add(etapa)

    # Autorização da equipe: se o modelo tem representante(s) autorizado(s),
    # injeta etapa(s) JÁ SATISFEITA(S) por autorização prévia (não é assinatura
    # pessoal no ato — o método do manifesto deixa isso claro).
    if payload.modelo_id:
        from app.api.autorizacao_equipe import autorizacoes_ativas
        prox_ordem = max((e.ordem for e in etapas_in), default=0) + 1
        for aut in autorizacoes_ativas(db, payload.modelo_id):
            etapa = EtapaAssinatura(
                id=uuid.uuid4(), solicitacao_id=sol.id, papel=aut.papel,
                ordem=prox_ordem, tipo_signatario=TipoSignatario.externo,
                externo_nome=aut.nome, externo_email=aut.email, externo_cpf=aut.cpf,
                assinado_em=datetime.now(timezone.utc), assinante_nome=aut.nome,
                assinante_cpf=aut.cpf, hash_sha256=aut.hash_sha256,
                prova_metodo="autorizacao_previa")
            db.add(etapa)
            prox_ordem += 1

    registrar(db, "roteiro_assinatura_criado", ator="rh", ator_detalhe=rh.email,
              candidato_id=cand.id, detalhe={"titulo": titulo, "etapas": len(etapas_in)})
    db.commit()
    return _dump_sol(db, sol)


def _titulo_corpo(db: Session, payload: NovaSolicitacaoIn) -> tuple[str, str | None]:
    if payload.modelo_id:
        from app.models.modelo_documento import ModeloDocumento
        m = db.get(ModeloDocumento, payload.modelo_id)
        if m is None:
            raise HTTPException(status_code=404, detail="modelo_nao_encontrado")
        return m.titulo[:200], m.corpo
    from app.api.assinaturas import NOMES_DOC
    from app.models.assinatura import DocumentoAssinavel
    try:
        return NOMES_DOC[DocumentoAssinavel(payload.documento)], None
    except (ValueError, KeyError):
        raise HTTPException(status_code=422, detail="documento_invalido")


@router.post("/rh/solicitacoes-assinatura/{sol_id}/disparar",
             dependencies=[Depends(requer_rh)])
def disparar(sol_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    sol = db.get(SolicitacaoAssinatura, sol_id)
    if sol is None:
        raise HTTPException(status_code=404, detail="solicitacao_nao_encontrada")
    if sol.status != StatusSolicitacao.rascunho:
        raise HTTPException(status_code=409, detail="ja_disparada")
    etapas = db.scalars(select(EtapaAssinatura)
                        .where(EtapaAssinatura.solicitacao_id == sol.id)).all()
    sol.etapa_atual_ordem = min(e.ordem for e in etapas)
    sol.status = StatusSolicitacao.aguardando
    registrar(db, "roteiro_assinatura_disparado", ator="rh", ator_detalhe=rh.email,
              candidato_id=sol.candidato_id)
    db.commit()
    # notifica a 1ª ordem (fora da transação)
    _notificar_liberadas(db, sol, [e for e in etapas if e.ordem == sol.etapa_atual_ordem],
                         base_url_publica(request))
    return _dump_sol(db, sol)


@router.get("/rh/candidatos/{cid}/solicitacoes-assinatura",
            dependencies=[Depends(requer_rh)])
def listar_do_candidato(cid: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    sols = db.scalars(select(SolicitacaoAssinatura)
                      .where(SolicitacaoAssinatura.candidato_id == cid)
                      .order_by(SolicitacaoAssinatura.criado_em.desc())).all()
    return {"solicitacoes": [_dump_sol(db, s) for s in sols]}


class CancelarIn(BaseModel):
    motivo: str | None = None


@router.post("/rh/solicitacoes-assinatura/{sol_id}/cancelar",
             dependencies=[Depends(requer_rh)])
def cancelar(sol_id: uuid.UUID, payload: CancelarIn, db: Session = Depends(get_db),
             rh: UsuarioRH = Depends(requer_rh)) -> dict:
    sol = db.get(SolicitacaoAssinatura, sol_id)
    if sol is None:
        raise HTTPException(status_code=404, detail="solicitacao_nao_encontrada")
    if sol.status in (StatusSolicitacao.concluida, StatusSolicitacao.cancelada):
        raise HTTPException(status_code=409, detail="nao_cancelavel")
    sol.status = StatusSolicitacao.cancelada
    sol.cancelada_motivo = (payload.motivo or "").strip()[:300] or None
    # revoga tokens externos pendentes (correção C2)
    for e in db.scalars(select(EtapaAssinatura).where(
            EtapaAssinatura.solicitacao_id == sol.id,
            EtapaAssinatura.assinado_em.is_(None))).all():
        e.token_hash = None
        e.otp_hash = None
    registrar(db, "roteiro_assinatura_cancelado", ator="rh", ator_detalhe=rh.email,
              candidato_id=sol.candidato_id, detalhe={"motivo": sol.cancelada_motivo})
    db.commit()
    return _dump_sol(db, sol)


# ---------------------------------------------------------------------------
# Fila do RH: documentos aguardando MINHA assinatura
# ---------------------------------------------------------------------------


@router.get("/rh/minhas-assinaturas")
def minhas_assinaturas(db: Session = Depends(get_db),
                       rh: UsuarioRH = Depends(requer_rh)) -> dict:
    # etapas usuario_rh minhas, na vez, ainda não assinadas, solicitação aguardando
    etapas = db.scalars(
        select(EtapaAssinatura)
        .join(SolicitacaoAssinatura,
              EtapaAssinatura.solicitacao_id == SolicitacaoAssinatura.id)
        .where(EtapaAssinatura.tipo_signatario == TipoSignatario.usuario_rh,
               EtapaAssinatura.usuario_rh_id == rh.id,
               EtapaAssinatura.assinado_em.is_(None),
               EtapaAssinatura.recusada_em.is_(None),
               SolicitacaoAssinatura.status == StatusSolicitacao.aguardando,
               EtapaAssinatura.ordem == SolicitacaoAssinatura.etapa_atual_ordem)).all()
    saida = []
    for e in etapas:
        sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
        cand = db.get(Candidato, sol.candidato_id)
        saida.append({"etapa_id": e.id, "papel": e.papel,
                      "titulo": sol.titulo_doc or sol.documento,
                      "colaborador": cand.nome_completo if cand else "-",
                      "criado_em": sol.criado_em})
    return {"pendentes": saida}


@router.get("/rh/minhas-assinaturas/feitas")
def minhas_assinaturas_feitas(db: Session = Depends(get_db),
                              rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """O que EU já assinei (etapas usuario_rh minhas com assinado_em)."""
    etapas = db.scalars(
        select(EtapaAssinatura)
        .where(EtapaAssinatura.tipo_signatario == TipoSignatario.usuario_rh,
               EtapaAssinatura.usuario_rh_id == rh.id,
               EtapaAssinatura.assinado_em.isnot(None))
        .order_by(EtapaAssinatura.assinado_em.desc())).all()
    saida = []
    for e in etapas:
        sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
        cand = db.get(Candidato, sol.candidato_id) if sol else None
        saida.append({
            "etapa_id": e.id, "papel": e.papel,
            "titulo": sol.titulo_doc or sol.documento if sol else "-",
            "colaborador": cand.nome_completo if cand else "-",
            "assinado_em": e.assinado_em,
            "documento_concluido": sol.status == StatusSolicitacao.concluida if sol else False,
        })
    return {"feitas": saida}


@router.get("/rh/solicitacoes-assinatura")
def listar_todas(db: Session = Depends(get_db),
                 _rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Todos os roteiros (para a aba Gerenciar) — visão geral do RH."""
    sols = db.scalars(select(SolicitacaoAssinatura)
                      .order_by(SolicitacaoAssinatura.criado_em.desc())).all()
    saida = []
    for s in sols:
        cand = db.get(Candidato, s.candidato_id)
        etapas = db.scalars(select(EtapaAssinatura)
                            .where(EtapaAssinatura.solicitacao_id == s.id)).all()
        assinadas = sum(1 for e in etapas if e.assinado_em is not None)
        saida.append({
            "id": s.id, "titulo": s.titulo_doc or s.documento, "status": s.status,
            "colaborador": cand.nome_completo if cand else "-",
            "criado_em": s.criado_em, "progresso": f"{assinadas}/{len(etapas)}",
            "pdf_final": bool(s.pdf_final_key), "candidato_id": s.candidato_id,
        })
    return {"solicitacoes": saida}


class AssinarRhIn(BaseModel):
    senha: str


@router.post("/rh/etapas/{etapa_id}/assinar")
def assinar_etapa_rh(etapa_id: uuid.UUID, payload: AssinarRhIn, request: Request,
                     db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Usuário do RH assina a etapa dele, provando presença com a senha."""
    exigir(f"assin-rh:{rh.id}", maximo=MAX_TENTATIVAS_SENHA, janela_s=900)
    e = db.get(EtapaAssinatura, etapa_id)
    if e is None:
        raise HTTPException(status_code=404, detail="etapa_nao_encontrada")
    # C4: o usuário logado tem de SER o signatário daquela etapa
    if e.tipo_signatario != TipoSignatario.usuario_rh or e.usuario_rh_id != rh.id:
        raise HTTPException(status_code=403, detail="etapa_nao_e_sua")
    if e.assinado_em is not None:
        raise HTTPException(status_code=409, detail="etapa_ja_assinada")
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    if sol.status != StatusSolicitacao.aguardando or e.ordem != sol.etapa_atual_ordem:
        raise HTTPException(status_code=409, detail="fora_da_vez")
    if not verificar_senha(payload.senha, rh.senha_hash):
        raise HTTPException(status_code=401, detail="senha_invalida")

    # guarda idempotente: só assina se ainda não estava assinada
    agora = datetime.now(timezone.utc)
    e.assinado_em = agora
    e.assinante_nome = rh.nome
    e.assinante_cpf = None
    e.ip = ip_do_cliente(request)
    e.user_agent = request.headers.get("user-agent", "")[:400]
    e.prova_metodo = "senha_sessao_rh"
    e.hash_sha256 = hashlib.sha256(
        f"{sol.id}:{e.id}:{rh.id}:{agora.isoformat()}".encode()).hexdigest()
    registrar(db, "etapa_assinada", ator="rh", ator_detalhe=rh.email,
              candidato_id=sol.candidato_id,
              detalhe={"papel": e.papel, "metodo": "senha_sessao_rh"})
    db.commit()
    resultado = avancar_solicitacao(db, sol.id)
    db.commit()
    _notificar_liberadas(db, sol, resultado["notificar"], base_url_publica(request))
    return {"assinado": True, "concluida": resultado["concluida"]}


class RecusarIn(BaseModel):
    motivo: str


@router.post("/rh/etapas/{etapa_id}/recusar")
def recusar_etapa_rh(etapa_id: uuid.UUID, payload: RecusarIn,
                     db: Session = Depends(get_db),
                     rh: UsuarioRH = Depends(requer_rh)) -> dict:
    """Recusa != cancelamento (correção M6): a solicitação vai a pendente_rh e o
    RH decide reatribuir a etapa; as anteriores já assinadas NÃO se perdem."""
    e = db.get(EtapaAssinatura, etapa_id)
    if e is None or e.usuario_rh_id != rh.id:
        raise HTTPException(status_code=404, detail="etapa_nao_encontrada")
    if e.assinado_em is not None:
        raise HTTPException(status_code=409, detail="etapa_ja_assinada")
    e.recusada_em = datetime.now(timezone.utc)
    e.recusada_motivo = payload.motivo.strip()[:300]
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    sol.status = StatusSolicitacao.pendente_rh
    registrar(db, "etapa_recusada", ator="rh", ator_detalhe=rh.email,
              candidato_id=sol.candidato_id, detalhe={"papel": e.papel, "motivo": e.recusada_motivo})
    db.commit()
    return {"recusada": True}


# ---------------------------------------------------------------------------
# Hook chamado quando o CANDIDATO assina (do fluxo de link mágico)
# ---------------------------------------------------------------------------


def promover_etapa_do_candidato(db: Session, assinatura: Assinatura,
                                base_url: str | None = None) -> None:
    """Chamado após o candidato assinar uma Assinatura que pertence a um roteiro
    (tem solicitacao_etapa_id). Copia as evidências para a etapa e avança."""
    if not assinatura.solicitacao_etapa_id:
        return
    e = db.get(EtapaAssinatura, uuid.UUID(assinatura.solicitacao_etapa_id))
    if e is None or e.assinado_em is not None:
        return
    cand = db.get(Candidato, assinatura.candidato_id)
    from app.models.ficha import DocumentosIdentificacao
    d = db.get(DocumentosIdentificacao, cand.id)
    e.assinado_em = assinatura.assinado_em
    e.assinante_nome = cand.nome_completo
    e.assinante_cpf = d.cpf if d else cand.cpf
    e.hash_sha256 = assinatura.hash_sha256
    e.pdf_key = assinatura.pdf_key
    e.ip = assinatura.ip
    e.user_agent = assinatura.user_agent
    e.prova_metodo = "otp_email"
    db.commit()
    sol = db.get(SolicitacaoAssinatura, e.solicitacao_id)
    resultado = avancar_solicitacao(db, sol.id)
    db.commit()
    _notificar_liberadas(db, sol, resultado["notificar"], base_url)


# ---------------------------------------------------------------------------
# Notificação das etapas liberadas — SEMPRE após commit (correção M7)
# ---------------------------------------------------------------------------


def _notificar_liberadas(db: Session, sol: SolicitacaoAssinatura,
                         etapas: list[EtapaAssinatura], base_url: str | None) -> None:
    from app.api.solicitacoes_externo import emitir_link_etapa
    from app.services.email import enviar_email, html_moderno
    for e in etapas:
        if e.tipo_signatario == TipoSignatario.externo and e.externo_email:
            link = emitir_link_etapa(db, e, base_url)
            db.commit()
            enviar_email(
                e.externo_email,
                f"Green House — documento aguarda sua assinatura ({e.papel})",
                f"Olá, {e.externo_nome}!\n\nUm documento aguarda a sua assinatura "
                f"eletrônica na qualidade de {e.papel}.\n\nAcesse: {link}\n",
                html_moderno("Documento aguarda sua assinatura", [
                    f"Olá, <strong>{e.externo_nome}</strong>!",
                    f"Um documento aguarda a sua assinatura eletrônica, na qualidade "
                    f"de <strong>{e.papel}</strong>.",
                    f"<a href='{link}'>Toque aqui para conferir e assinar</a>."]))
        # usuário RH: aparece na fila /rh/minhas-assinaturas (sem e-mail obrigatório)
        # candidato: assina pelo link mágico dele, já existente
