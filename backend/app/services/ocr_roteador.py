"""Roteamento da leitura automatizada por SENSIBILIDADE do documento (Onda B).

O sistema já lia documentos com IA (`ocr_ia.py`, Mistral OCR + fallback local),
mas tratava todo documento igual. A partir da Onda B há documento de SAÚDE na
jogada (ASO do brigadista), que é categoria especial da LGPD (art. 11) — e a
verificação da Mistral (2026-07-22) mostrou que:

- a API paga **não treina** com o dado, mas
- a retenção padrão é de **30 dias** para monitoramento de abuso, e
- o **Zero Data Retention só existe no plano Scale, mediante pedido aprovado**.

Reter dado de saúde por 30 dias num terceiro, sem necessidade, contraria o
princípio da necessidade. Então a trava fica **no código**, não numa política
que alguém esquece: sem ZDR ligado na configuração, documento de saúde não é
enviado para a IA — e o resto do módulo continua funcionando normalmente.

Regra de ouro herdada da casa: a IA **propõe**, o humano **confirma**. Nada
aqui grava coisa alguma.
"""

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.desenvolvimento import SensibilidadeDoc

log = logging.getLogger(__name__)
auditoria_log = logging.getLogger("telemetria")

# Chave da config dinâmica: o RH liga isto DEPOIS de a Mistral aprovar o Zero
# Data Retention no plano Scale. Enquanto estiver desligada, nenhum documento
# de saúde sai da VPS.
CHAVE_ZDR = "mistral_zdr_ativo"

_MIME_POR_EXT = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "webp": "image/webp",
}


def zdr_ativo(db: Session) -> bool:
    """O Zero Data Retention está confirmado na configuração?"""
    from app.services.config_dinamica import ler_config
    return (ler_config(db, (CHAVE_ZDR,)).get(CHAVE_ZDR) or "").strip().lower() \
        in ("1", "true", "sim")


def pode_ler_com_ia(db: Session, sensibilidade: SensibilidadeDoc) -> tuple[bool, str]:
    """(pode?, motivo). O motivo é para log e para a tela dizer à pessoa por que
    não houve pré-preenchimento — nunca deixar o usuário no escuro."""
    from app.services.ocr_ia import chave_mistral
    if not chave_mistral(db):
        return False, "sem_chave"
    if sensibilidade == SensibilidadeDoc.saude and not zdr_ativo(db):
        # A trava. Sai sozinha quando o ZDR for aprovado e ligado no painel.
        return False, "saude_sem_zdr"
    return True, "ok"


def ler_documento(db: Session, dados: bytes, ext: str,
                  sensibilidade: SensibilidadeDoc,
                  candidato_id=None) -> tuple[str | None, str]:
    """Texto do documento, respeitando a sensibilidade. Devolve (texto, motivo).

    `texto` é None quando não deu para ler — o chamador segue sem sugestão, o
    que é sempre aceitável: o formulário só perde o pré-preenchimento.

    Registra a leitura de documento SENSÍVEL na auditoria, com hash e nunca
    conteúdo — é o que prova, numa fiscalização, o que foi lido e quando.
    """
    pode, motivo = pode_ler_com_ia(db, sensibilidade)
    sha = hashlib.sha256(dados).hexdigest()
    if not pode:
        if motivo == "saude_sem_zdr":
            log.info("Leitura de documento de saúde bloqueada: ZDR não ativo.")
        return None, motivo

    mime = _MIME_POR_EXT.get((ext or "").lower().lstrip("."), "image/jpeg")
    from app.services.ocr_ia import texto_via_mistral
    texto = texto_via_mistral(dados, mime)

    if sensibilidade in (SensibilidadeDoc.saude, SensibilidadeDoc.identidade):
        _auditar_leitura(db, sensibilidade, sha, len(dados), bool(texto), candidato_id)
    return (texto or None), ("ok" if texto else "sem_texto")


def _auditar_leitura(db: Session, sensibilidade: SensibilidadeDoc, sha: str,
                     tamanho: int, houve_texto: bool, candidato_id) -> None:
    """Trilha da leitura de documento sensível: quem, quando, qual tipo, hash.
    **Nunca o conteúdo** — nem trecho, nem campo extraído."""
    from app.services.auditoria import registrar
    registrar(db, "documento_lido_por_ia", ator="sistema",
              candidato_id=candidato_id,
              detalhe={"sensibilidade": sensibilidade.value,
                       "sha256": sha[:16], "bytes": tamanho,
                       "provedor": "mistral", "resultado": "ok" if houve_texto else "vazio"})
    auditoria_log.info(
        "leitura_ia sensibilidade=%s sha256=%s bytes=%s ok=%s",
        sensibilidade.value, sha[:16], tamanho, int(houve_texto))


def carimbar_leitura(registro, extraido: dict | None) -> None:
    """Guarda no registro o que a IA propôs, para comparar com o que a pessoa
    confirmou depois (auditoria e medição de qualidade da extração)."""
    registro.extraido_ia = extraido or None
    registro.lido_por_ia_em = datetime.now(timezone.utc) if extraido else None
