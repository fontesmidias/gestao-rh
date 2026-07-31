"""Expurgo de arquivos no MinIO (LGPD + espaço em disco).

Candidatos aprovados há mais de RETENTION_DAYS têm os arquivos soltos removidos
(originais e PDFs por slot). O dossiê final é mantido — é o registro trabalhista.
Rode: python -m app.workers.expurgo (o compose agenda diariamente).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.candidato import Candidato, StatusCandidato
from app.models.documento import SlotDocumento
from app.services import storage

log = logging.getLogger(__name__)


def _arquivos_do_slot(slot: SlotDocumento) -> list[str]:
    """TODOS os arquivos do slot no storage, não só os dois do registro.

    Um envio pode ter várias partes (frente e verso do RG, páginas de
    certidão): `_gravar_partes_no_slot` grava `original/{i}-{nome}` para cada
    uma, mas o registro guarda a key de UMA só (`arquivo_original_key`, a
    primeira). Expurgar pelo registro deixava o VERSO no MinIO para sempre —
    dado pessoal que a retenção diz que já não deveria existir, e que nenhuma
    tela mostra para alguém notar a sobra. Por isso a lista vem do prefixo,
    como em `documentos.py::expurgar_arquivos_do_slot`; o registro é o
    fallback de quando o storage não lista.
    """
    base = f"candidatos/{slot.candidato_id}/slots/{slot.id}/"
    try:
        keys = storage.listar(base)
    except Exception:
        log.exception("Falha ao listar %s; caindo nas keys do registro", base)
        keys = []
    return keys or [k for k in (slot.arquivo_original_key, slot.arquivo_pdf_key) if k]


def expurgar() -> int:
    settings = get_settings()
    limite = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    total = 0
    with SessionLocal() as db:
        candidatos = db.scalars(
            select(Candidato).where(
                Candidato.status == StatusCandidato.aprovado,
                # SÓ admissão: quem já é colaborador (situacao preenchida) NÃO é
                # expurgado — efetivar agora deixa status=aprovado (v1.69), e o
                # colaborador ativo não pode ter os documentos apagados.
                Candidato.situacao.is_(None),
                Candidato.dossie_gerado_em < limite,
                Candidato.arquivos_expurgados_em.is_(None),
            )
        ).all()
        for cand in candidatos:
            slots = db.scalars(
                select(SlotDocumento).where(SlotDocumento.candidato_id == cand.id)
            ).all()
            for slot in slots:
                for key in _arquivos_do_slot(slot):
                    try:
                        storage.remover(key)
                    except Exception:
                        log.exception("Falha ao remover %s", key)
                slot.arquivo_original_key = None
                slot.arquivo_pdf_key = None
            cand.arquivos_expurgados_em = datetime.now(timezone.utc)
            total += 1
            log.info("Arquivos expurgados: %s", cand.nome_completo)
        db.commit()
    return total


def expurgar_telemetria() -> int:
    """Aplica a retenção da telemetria de uso (v2.24).

    Mora aqui, e não num worker novo, porque o compose já agenda este diariamente
    — um cron a mais seria mais uma peça para esquecer de subir.

    A retenção é configurável no painel (padrão 1 ano, escolha do Bruno para
    permitir comparação sazonal). Telemetria NÃO passa pela lixeira: é dado
    descartável de produto, e milhões de linhas de uso afogariam a lixeira, que
    existe para proteger documento de gente.
    """
    from app.services.telemetria import expurgar as expurgar_tel, retencao_dias

    with SessionLocal() as db:
        dias = retencao_dias(db)
        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        n = expurgar_tel(db, antes_de=corte)
        db.commit()
        if n:
            log.info("Telemetria expurgada: %s eventos anteriores a %s (retenção de %s dias)",
                     n, corte.date(), dias)
        return n


def expurgar_logs() -> int:
    """Aplica a retenção dos arquivos de log (v2.29).

    Mesma carona do expurgo diário, pelo mesmo motivo da telemetria. **Retenção
    0 = indeterminado** e não apaga nada — opção que o Bruno pediu
    explicitamente. O log CORRENTE nunca é removido, só os rotacionados por dia.
    """
    from app.services.logs import expurgar as expurgar_logs_svc, retencao_dias

    with SessionLocal() as db:
        dias = retencao_dias(db)
    if dias <= 0:
        log.info("Retenção de logs indeterminada; nada a expurgar.")
        return 0
    n = expurgar_logs_svc(dias)
    if n:
        log.info("Logs expurgados: %s arquivo(s) com mais de %s dias", n, dias)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Candidatos expurgados: {expurgar()}")
    print(f"Eventos de telemetria expurgados: {expurgar_telemetria()}")
    print(f"Arquivos de log expurgados: {expurgar_logs()}")
