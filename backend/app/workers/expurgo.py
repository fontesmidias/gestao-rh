"""Expurgo de arquivos no MinIO (LGPD + espaço em disco).

Candidatos aprovados há mais de RETENTION_DAYS têm os arquivos soltos removidos
(originais e PDFs por slot). O dossiê final é mantido — é o registro trabalhista.
Rode: python -m app.workers.expurgo (o compose agenda diariamente).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

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


def arquivar_entrevistas() -> int:
    """Arquiva entrevistas antigas (v2.64) — **ARQUIVA, NÃO APAGA**.

    Decisão do Bruno (2026-08-04), fora do menu de três opções que a sala
    ofereceu — todas assumiam apagar algo. Arquivar resolve a tensão que as
    outras não resolviam:

    - nota velha não deve assombrar quem se candidata de novo dois anos depois;
    - mas reentrevistar quem faltou três vezes sem saber é desperdício.

    O julgamento vencido sai da vista e das métricas; a memória continua
    acessível a quem procurar (`?incluir_arquivadas=true`).

    ⚠️ Se algum dia isto virar `db.delete`, é REGRESSÃO — há teste por mutação
    (`test_entrevistas.py`, bloco 7) que reprova a troca.

    **Quem virou colaborador fica FORA do prazo** (cenário 14): a entrevista de
    movimentação interna é parte do vínculo, não material de recrutamento com
    validade. Por isso o filtro exige `candidato_id IS NULL` OU candidato sem
    `situacao` — quem tem vínculo ativo/desligado não entra na varredura.

    Retenção configurável (padrão 180 dias). **0 = indeterminado**, e então
    nada é arquivado — mesma convenção da retenção de logs; trocar por
    `is not None` transformaria "guardar para sempre" em "arquivar tudo hoje".
    """
    from app.models.candidato import Candidato
    from app.models.entrevista import Entrevista, StatusEntrevista
    from app.services.config_dinamica import ler_config
    from app.services.entrevistas import RETENCAO_PADRAO_DIAS

    with SessionLocal() as db:
        try:
            cfg = ler_config(db, ("entrevistas_retencao_dias",))
            dias = int(cfg.get("entrevistas_retencao_dias") or RETENCAO_PADRAO_DIAS)
        except (TypeError, ValueError):
            dias = RETENCAO_PADRAO_DIAS
        if dias <= 0:
            log.info("Retenção de entrevistas indeterminada; nada a arquivar.")
            return 0

        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        # A data de referência é quando a entrevista ACONTECEU (ou, na falta,
        # quando foi criada) — não a de preenchimento: preencher tarde não pode
        # esticar a validade do julgamento.
        candidatas = db.scalars(
            select(Entrevista).where(
                Entrevista.status != StatusEntrevista.arquivada.value,
                func.coalesce(Entrevista.realizada_em,
                              Entrevista.marcada_para,
                              Entrevista.criada_em) < corte,
            )).all()

        # Colaborador (situacao preenchida) fica de fora — parte do vínculo.
        com_vinculo = set()
        cids = [e.candidato_id for e in candidatas if e.candidato_id]
        if cids:
            com_vinculo = {
                c_id for c_id in db.scalars(
                    select(Candidato.id).where(Candidato.id.in_(cids),
                                               Candidato.situacao.is_not(None)))}

        n = 0
        agora = datetime.now(timezone.utc)
        for e in candidatas:
            if e.candidato_id and e.candidato_id in com_vinculo:
                continue
            e.status = StatusEntrevista.arquivada
            e.arquivada_em = agora
            n += 1
        db.commit()
        if n:
            log.info("Entrevistas arquivadas: %s com mais de %s dias (o registro "
                     "PERMANECE, só sai da vista)", n, dias)
        return n


def expurgar_audio_entrevistas() -> int:
    """Apaga o ÁUDIO das entrevistas passada a retenção (v2.98.3, padrão 120
    dias, configurável no painel).

    **O áudio expira; o TEXTO permanece.** Voz é dado pessoal — há entendimento
    de que é biométrico — e guardá-la para sempre é difícil de justificar. A
    transcrição é o que serve para escrever a justificativa da avaliação, e
    permanece: apagá-la junto tiraria a razão de o módulo existir.

    Três decisões que NÃO devem ser afrouxadas:

    1. **Retenção `0` = INDETERMINADO**, não "apagar tudo hoje" (mesma convenção
       do log, v2.29). ⚠️ Trocar `<= 0` por `is not None` inverteria o
       significado e apagaria a base inteira em silêncio.
    2. **Conta a partir da GRAVAÇÃO, não da criação da entrevista.** Uma
       entrevista marcada em janeiro e gravada em junho tem áudio de junho.
    3. **O REGISTRO permanece** (com o carimbo `audio_expurgado_em` implícito no
       estado): apagar a linha apagaria a prova de que a pessoa foi consultada e
       consentiu, que é justamente o que ela existe para provar.
    """
    from app.models.bloco_gravacao import BlocoGravacao
    from app.models.gravacao_entrevista import GravacaoEntrevista
    from app.services import storage
    from app.services.gravacao_entrevista import config

    with SessionLocal() as db:
        dias = config(db)["retencao_dias"]
        if dias <= 0:                      # ver decisão 1
            return 0
        corte = datetime.now(timezone.utc) - timedelta(days=dias)
        alvos = db.scalars(select(GravacaoEntrevista).where(
            GravacaoEntrevista.gravado_em.isnot(None),
            GravacaoEntrevista.gravado_em < corte)).all()

        removidos = 0
        for g in alvos:
            blocos = db.scalars(select(BlocoGravacao).where(
                BlocoGravacao.gravacao_id == g.id)).all()
            chaves = [g.audio_key, *[b.audio_key for b in blocos]]
            if not any(chaves):
                continue                   # já expurgada numa passada anterior
            for key in chaves:
                if not key:
                    continue
                try:
                    storage.remover(key)
                    removidos += 1
                except Exception:          # noqa: BLE001
                    # Não trava o lote — mas REGISTRA: falha ao remover dado
                    # pessoal não pode ser silêncio.
                    log.exception("Áudio não removido no expurgo: %s", key)
            g.audio_key = g.audio_bytes = g.audio_tipo = None
            for b in blocos:
                b.audio_key = b.audio_bytes = b.audio_tipo = None
        db.commit()
        if removidos:
            log.info("Áudio de entrevista expurgado: %s arquivo(s) anteriores a %s "
                     "(retenção de %s dias). As transcrições foram mantidas.",
                     removidos, corte.date(), dias)
        return removidos


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Candidatos expurgados: {expurgar()}")
    print(f"Eventos de telemetria expurgados: {expurgar_telemetria()}")
    print(f"Arquivos de log expurgados: {expurgar_logs()}")
    print(f"Entrevistas arquivadas: {arquivar_entrevistas()}")
    print(f"Áudios de entrevista expurgados: {expurgar_audio_entrevistas()}")
