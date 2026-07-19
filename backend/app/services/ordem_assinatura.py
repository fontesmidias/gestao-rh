"""Ordem configurável em que as fichas-base aparecem para o candidato assinar e
no dossiê. Antes era fixa no código (ORDEM_FICHAS); agora o RH pode reordenar
pela tela de assinaturas — guardada na config dinâmica.

A ordem é uma lista de valores de DocumentoAssinavel (as 4 fichas-base). Se a
config estiver ausente ou incompleta, cai na ordem-padrão histórica e completa
com o que faltar (nenhuma ficha some por causa de config velha)."""

import json

from sqlalchemy.orm import Session

from app.models.assinatura import FICHAS_BASE, DocumentoAssinavel
from app.services.config_dinamica import gravar_config, ler_config

_CHAVE = "ordem_assinatura_fichas"
# Ordem-padrão = a histórica (a mesma de dossie.ORDEM_FICHAS).
_PADRAO = [d.value for d in FICHAS_BASE]


def ordem_fichas(db: Session) -> list[DocumentoAssinavel]:
    """As fichas-base na ordem configurada. Sempre devolve TODAS as 4 (config
    parcial é completada com as que faltam, na ordem-padrão)."""
    bruto = ler_config(db, (_CHAVE,)).get(_CHAVE)
    salva: list[str] = []
    if bruto:
        try:
            salva = [v for v in json.loads(bruto) if v in _PADRAO]
        except (ValueError, TypeError):
            salva = []
    # completa com o que faltar, preservando a ordem-padrão
    for v in _PADRAO:
        if v not in salva:
            salva.append(v)
    return [DocumentoAssinavel(v) for v in salva]


def salvar_ordem(db: Session, ordem: list[str]) -> list[str]:
    """Grava a nova ordem (só aceita os valores das fichas-base; ignora o resto)."""
    limpa = [v for v in ordem if v in _PADRAO]
    for v in _PADRAO:
        if v not in limpa:
            limpa.append(v)
    gravar_config(db, {_CHAVE: json.dumps(limpa)})
    db.commit()
    return limpa
