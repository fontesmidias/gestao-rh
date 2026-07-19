"""Expiração de roteiros de assinatura vencidos + higienização LGPD dos dados de
signatários externos que não chegaram a assinar.

Um roteiro `aguardando` cujo `expira_em` passou vira `expirada`; seus tokens e
OTPs pendentes são revogados. Vias JÁ assinadas ficam intactas (são prova do
ato). Além disso, dados pessoais de externos (email/cpf/token/otp) de etapas NÃO
assinadas de roteiros encerrados (cancelados/expirados) há mais de
RETENTION_DAYS são zerados — minimização (LGPD): não guardamos dado de terceiro
que não virou assinatura além do necessário.

Rode: python -m app.workers.expirar_roteiros (o compose agenda diariamente).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.solicitacao_assinatura import (EtapaAssinatura,
                                               SolicitacaoAssinatura,
                                               StatusSolicitacao)

log = logging.getLogger(__name__)


def expirar_vencidos(db) -> int:
    agora = datetime.now(timezone.utc)
    vencidas = db.scalars(
        select(SolicitacaoAssinatura).where(
            SolicitacaoAssinatura.status == StatusSolicitacao.aguardando,
            SolicitacaoAssinatura.expira_em.isnot(None),
            SolicitacaoAssinatura.expira_em < agora)).all()
    for sol in vencidas:
        sol.status = StatusSolicitacao.expirada
        # revoga o acesso das etapas ainda não assinadas
        for e in db.scalars(select(EtapaAssinatura).where(
                EtapaAssinatura.solicitacao_id == sol.id,
                EtapaAssinatura.assinado_em.is_(None))).all():
            e.token_hash = None
            e.otp_hash = None
        log.info("Roteiro expirado: %s", sol.id)
    return len(vencidas)


def higienizar_externos(db) -> int:
    """Zera dados pessoais de externos em etapas NÃO assinadas de roteiros já
    encerrados (cancelados/expirados) há mais do prazo de retenção."""
    limite = datetime.now(timezone.utc) - timedelta(days=get_settings().retention_days)
    encerradas = db.scalars(
        select(SolicitacaoAssinatura).where(
            SolicitacaoAssinatura.status.in_((StatusSolicitacao.cancelada,
                                             StatusSolicitacao.expirada)),
            SolicitacaoAssinatura.atualizado_em < limite)).all()
    total = 0
    for sol in encerradas:
        for e in db.scalars(select(EtapaAssinatura).where(
                EtapaAssinatura.solicitacao_id == sol.id,
                EtapaAssinatura.assinado_em.is_(None),
                EtapaAssinatura.externo_email.isnot(None))).all():
            e.externo_email = None
            e.externo_cpf = None
            e.token_hash = None
            e.otp_hash = None
            total += 1
    return total


def executar() -> tuple[int, int]:
    with SessionLocal() as db:
        expiradas = expirar_vencidos(db)
        higienizados = higienizar_externos(db)
        db.commit()
    return expiradas, higienizados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    exp, hig = executar()
    print(f"Roteiros expirados: {exp} | dados de externos higienizados: {hig}")
