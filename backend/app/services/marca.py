"""Identidade da empresa (marca) configurável pelo painel, para desvincular o
sistema de uma empresa específica sem quebrar o padrão atual.

Os dados vêm da config dinâmica (banco); na ausência, caem nos valores-padrão
históricos (Green House) — nada muda até o RH customizar. A logo e o favicon
customizados ficam no MinIO e são servidos por endpoint próprio."""

from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

# Padrões históricos (o que estava chumbado). Viram só o valor inicial.
_PADRAO = {
    "empresa_nome": "Green House",
    "empresa_razao": "GREEN HOUSE SERVIÇOS DE LOCAÇÃO DE MÃO DE OBRA LTDA",
    "empresa_cnpj": "12.531.678/0001-80",
    "empresa_endereco": "SCIA Quadra 15, Conjunto 13, Lote 8, Zona Industrial (Guará), "
                        "Brasília/DF, CEP 71.250-015",
    "empresa_contato": "+55 61 3346-8812 | www.greenhousedf.com.br",
}
CHAVES = tuple(_PADRAO) + ("empresa_logo_key", "empresa_favicon_key")


def dados_empresa(db: Session) -> dict:
    """Dados da empresa efetivos: banco > padrão."""
    banco = ler_config(db, CHAVES)
    dados = {k: (banco.get(k) or v) for k, v in _PADRAO.items()}
    dados["logo_key"] = banco.get("empresa_logo_key") or None
    dados["favicon_key"] = banco.get("empresa_favicon_key") or None
    return dados


def salvar_dados(db: Session, valores: dict) -> None:
    """Grava só os campos de texto conhecidos (logo/favicon vão por upload)."""
    limpos = {k: str(valores[k]).strip() for k in _PADRAO if k in valores}
    if limpos:
        gravar_config(db, limpos)
        db.commit()
