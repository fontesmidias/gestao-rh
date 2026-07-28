"""Extração e cache do texto do currículo (v2.00).

O currículo NÃO MUDA depois do upload — então reler 131 currículos a cada
clique em "Ranquear" era desperdício puro (e, com OCR, garantia de estourar o
timeout de 60s do nginx). Aqui o texto é extraído UMA VEZ e guardado em
`CurriculoTexto`, já minimizado.

Quem chama:
- `POST /talentos/{id}/curriculo` (upload) → enfileira a extração
- worker de backfill → cobre os currículos que já estavam na base

A extração NUNCA levanta para o chamador: falha vira registro com
`legivel=False` + `motivo_falha`, para o RH ver na aba de Resultados que
`.heic` tem conserto e que PDF escaneado precisa de OCR configurado."""

import logging

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.match import CurriculoTexto
from app.models.talento import Talento
from app.services import storage
from app.services.curriculo_texto import CurriculoIlegivel, extrair_texto, minimizar

log = logging.getLogger(__name__)


def _nome_para_extensao(talento: Talento) -> str:
    """Nome do arquivo para o despacho por extensão. Cai para a
    `curriculo_key` quando `curriculo_nome` é NULL — talento importado de
    planilha costuma não ter nome, e antes isso o tornava 'ilegível' mesmo
    com o arquivo certo no MinIO (bug encontrado no diagnóstico de
    2026-07-28)."""
    if talento.curriculo_nome and "." in talento.curriculo_nome:
        return talento.curriculo_nome
    return talento.curriculo_key or ""


def indexar_talento(talento_id) -> dict:
    """Extrai (ou reextrai) o texto do currículo de UM talento. Idempotente:
    se já existe texto para a mesma `curriculo_key`, não refaz."""
    with SessionLocal() as db:
        talento = db.get(Talento, talento_id)
        if talento is None:
            return {"ok": False, "motivo": "talento_nao_encontrado"}

        registro = db.get(CurriculoTexto, talento.id)

        if not talento.curriculo_key:
            # Sem currículo: registra o fato (a aba de Resultados mostra
            # "sem currículo" em vez de sumir com a pessoa).
            if registro is None:
                registro = CurriculoTexto(talento_id=talento.id)
                db.add(registro)
            registro.curriculo_key = None
            registro.texto = None
            registro.legivel = False
            registro.motivo_falha = "sem_curriculo"
            registro.caracteres = 0
            db.commit()
            return {"ok": False, "motivo": "sem_curriculo"}

        # Já indexado para ESTE arquivo: nada a fazer (idempotente)
        if registro is not None and registro.curriculo_key == talento.curriculo_key \
                and registro.legivel:
            return {"ok": True, "motivo": "ja_indexado", "caracteres": registro.caracteres}

        motivo = None
        texto = None
        try:
            dados = storage.ler(talento.curriculo_key)
            bruto = extrair_texto(dados, _nome_para_extensao(talento))
            texto = minimizar(bruto)   # guarda JÁ SEM CPF/RG/telefone/e-mail/CEP
        except CurriculoIlegivel as exc:
            motivo = str(exc)[:120]
        except Exception as exc:
            motivo = f"falha_leitura_{type(exc).__name__}"[:120]
            log.warning("Falha ao indexar currículo do talento %s (%s).",
                        talento_id, type(exc).__name__)

        if registro is None:
            registro = CurriculoTexto(talento_id=talento.id)
            db.add(registro)
        registro.curriculo_key = talento.curriculo_key
        registro.texto = texto
        registro.legivel = bool(texto)
        registro.motivo_falha = motivo
        registro.caracteres = len(texto) if texto else 0
        db.commit()

        return {"ok": bool(texto), "motivo": motivo, "caracteres": registro.caracteres}


def backfill(limite: int | None = None) -> dict:
    """Indexa os currículos que ainda não têm texto — os que já estavam na
    base antes da v2.00. Roda em background, um por vez; a leitura via OCR
    tem custo, então respeita `limite` quando informado."""
    with SessionLocal() as db:
        ja_indexados = {t for (t,) in db.execute(
            select(CurriculoTexto.talento_id).where(CurriculoTexto.legivel.is_(True)))}
        pendentes = [t.id for t in db.scalars(
            select(Talento).where(Talento.curriculo_key.isnot(None)))
            if t.id not in ja_indexados]

    if limite:
        pendentes = pendentes[:limite]

    ok = falhou = 0
    for tid in pendentes:
        resultado = indexar_talento(tid)
        if resultado.get("ok"):
            ok += 1
        else:
            falhou += 1
    log.info("Backfill de currículos: %s indexados, %s sem texto.", ok, falhou)
    return {"indexados": ok, "sem_texto": falhou, "total": len(pendentes)}
