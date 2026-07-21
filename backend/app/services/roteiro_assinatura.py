"""Motor do roteiro de assinatura multi-signatário: sequenciamento em ordem,
avanço serializado e consolidação do PDF final.

Invariantes (correções da revisão adversária):
- C3: `avancar_solicitacao` serializa com SELECT ... FOR UPDATE na solicitação
  desde o início e toda transição é idempotente.
- M7: notificações NUNCA são enviadas aqui (sob o lock / dentro da transação).
  Esta função apenas devolve QUEM notificar; o caller dispara após o commit.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                               SolicitacaoAssinatura,
                                               StatusSolicitacao)


def tem_roteiro(db: Session, candidato_id: uuid.UUID, *, documento: str | None = None,
                modelo_id: uuid.UUID | None = None) -> SolicitacaoAssinatura | None:
    """Devolve a solicitação ATIVA (não cancelada/expirada) para aquele
    documento/modelo daquele candidato, se existir — a decisão central de
    'este documento é multi-signatário?'."""
    q = select(SolicitacaoAssinatura).where(
        SolicitacaoAssinatura.candidato_id == candidato_id,
        SolicitacaoAssinatura.status.in_((StatusSolicitacao.rascunho,
                                          StatusSolicitacao.aguardando,
                                          StatusSolicitacao.pendente_rh,
                                          StatusSolicitacao.concluida)))
    if documento is not None:
        q = q.where(SolicitacaoAssinatura.documento == documento)
    if modelo_id is not None:
        q = q.where(SolicitacaoAssinatura.modelo_id == modelo_id)
    return db.scalar(q.order_by(SolicitacaoAssinatura.criado_em.desc()))


def _etapas(db: Session, sol: SolicitacaoAssinatura) -> list[EtapaAssinatura]:
    return db.scalars(select(EtapaAssinatura)
                      .where(EtapaAssinatura.solicitacao_id == sol.id)
                      .order_by(EtapaAssinatura.ordem, EtapaAssinatura.criado_em)).all()


def criar_roteiro_creche(db: Session, beneficio, rh) -> SolicitacaoAssinatura:
    """Cria e JÁ DISPARA o roteiro de assinatura do requerimento de creche:
    ordem 1 = colaborador (assina na própria sessão de creche, já 2FA — a etapa
    não aponta para Assinatura do wizard, `assinatura_id=None`), ordem 2 = o
    usuário RH que aprovou (contra-assina pela fila /rh/minhas-assinaturas).

    Idempotente: se já existe roteiro de creche ativo para o colaborador, devolve
    o existente (não recria a cada re-ativação)."""
    existente = tem_roteiro(db, beneficio.candidato_id)
    if existente is not None and existente.origem == "creche_requerimento":
        return existente
    sol = SolicitacaoAssinatura(
        candidato_id=beneficio.candidato_id,
        titulo_doc="Requerimento de Reembolso-Creche",
        origem="creche_requerimento",
        criada_por=getattr(rh, "email", None),
        status=StatusSolicitacao.aguardando,
        etapa_atual_ordem=1)
    db.add(sol)
    db.flush()
    db.add(EtapaAssinatura(
        id=uuid.uuid4(), solicitacao_id=sol.id, papel="Colaborador(a)",
        ordem=1, tipo_signatario="candidato"))
    db.add(EtapaAssinatura(
        id=uuid.uuid4(), solicitacao_id=sol.id, papel="Green House (RH)",
        ordem=2, tipo_signatario="usuario_rh", usuario_rh_id=rh.id))
    return sol


def avancar_solicitacao(db: Session, sol_id: uuid.UUID) -> dict:
    """Recalcula o estado do roteiro após uma etapa concluir, de forma
    SERIALIZADA e IDEMPOTENTE. Sobe `etapa_atual_ordem` quando todas as etapas
    da ordem corrente assinaram; conclui quando não há mais pendências.

    Devolve {"concluida": bool, "notificar": [etapas recém-liberadas]} — o
    caller notifica APÓS o commit. NUNCA envia e-mail aqui.
    """
    # trava a linha da solicitação (Postgres) — evita corrida de dois callbacks
    sol = db.scalar(select(SolicitacaoAssinatura)
                    .where(SolicitacaoAssinatura.id == sol_id)
                    .with_for_update())
    if sol is None or sol.status not in (StatusSolicitacao.aguardando,):
        return {"concluida": sol is not None and sol.status == StatusSolicitacao.concluida,
                "notificar": []}

    etapas = _etapas(db, sol)
    pendentes = [e for e in etapas if e.assinado_em is None and e.recusada_em is None]
    if not pendentes:
        # todas assinaram → conclui e consolida o PDF final
        sol.status = StatusSolicitacao.concluida
        _consolidar_pdf_final(db, sol, etapas)
        return {"concluida": True, "notificar": []}

    ordens_pendentes = sorted({e.ordem for e in pendentes})
    ordem_corrente = ordens_pendentes[0]
    subiu = ordem_corrente != sol.etapa_atual_ordem
    sol.etapa_atual_ordem = ordem_corrente
    # etapas que estão AGORA na vez (para notificar), só se acabamos de liberá-las
    liberadas = [e for e in pendentes if e.ordem == ordem_corrente] if subiu else []
    return {"concluida": False, "notificar": liberadas}


def _consolidar_pdf_final(db: Session, sol: SolicitacaoAssinatura,
                          etapas: list[EtapaAssinatura]) -> None:
    """Monta o PDF final com TODOS os blocos de assinatura empilhados + o
    manifesto multi-assinante, e grava no MinIO."""
    import hashlib

    from app.models.candidato import Candidato
    from app.services import storage
    from app.services.fichas import (VistoAssinatura, carimbar_rubrica_lateral,
                                     gerar_documento_com_vistos)

    candidato = db.get(Candidato, sol.candidato_id)
    vistos = [
        VistoAssinatura(
            nome=e.assinante_nome or "-", papel=e.papel,
            cpf=e.assinante_cpf, assinado_em=e.assinado_em, ip=e.ip,
            hash_sha256=e.hash_sha256, id_verificacao=str(e.id),
            metodo=e.prova_metodo or "")
        for e in etapas if e.assinado_em is not None
    ]
    if sol.origem == "creche_requerimento":
        # requerimento de creche: mantém o layout oficial (gerado por
        # creche_pdf) e empilha os blocos de visto + manifesto por cima.
        from app.models.beneficio import BeneficioCreche
        from app.services.creche_pdf import gerar_requerimento_creche
        ben = db.scalar(select(BeneficioCreche)
                        .where(BeneficioCreche.candidato_id == sol.candidato_id))
        pdf = gerar_requerimento_creche(db, ben, vistos=vistos, sol=sol)
    else:
        pdf = gerar_documento_com_vistos(db, sol, candidato, vistos)
    pdf = carimbar_rubrica_lateral_final(pdf, sol)
    key = f"candidatos/{sol.candidato_id}/assinaturas/{sol.id}/final.pdf"
    storage.salvar(key, pdf, "application/pdf")
    sol.pdf_final_key = key
    sol.hash_final_sha256 = hashlib.sha256(pdf).hexdigest()


def carimbar_rubrica_lateral_final(pdf: bytes, sol: SolicitacaoAssinatura) -> bytes:
    """Rubrica lateral no PDF final (usa o hash consolidado)."""
    from app.services.fichas import carimbar_rubrica_texto
    quando = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    texto = (f"Documento com {_conta_assinaturas(sol)} assinatura(s) | "
             f"solicitacao {sol.id} | {quando} | confira em /verificar-etapa")
    return carimbar_rubrica_texto(pdf, texto)


def _conta_assinaturas(sol: SolicitacaoAssinatura) -> str:
    return "multiplas"
