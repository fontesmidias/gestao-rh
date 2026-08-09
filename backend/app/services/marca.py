"""Identidade da empresa (marca) configurável pelo painel, para desvincular o
sistema de uma empresa específica sem quebrar o padrão atual.

Os dados vêm da config dinâmica (banco); na ausência, caem nos valores-padrão
históricos (Green House) — nada muda até o RH customizar. A logo e o favicon
customizados ficam no MinIO e são servidos por endpoint próprio."""

from sqlalchemy.orm import Session

from app.services.config_dinamica import gravar_config, ler_config

# --- Fonte da interface (v2.85) --------------------------------------------
#
# A fonte vale para o SISTEMA (painel e wizard), nunca para os DOCUMENTOS: o PDF
# é gerado pelo fpdf2 com fontes próprias, e o hash do ato de assinatura é
# calculado sobre ele — trocar a fonte do documento faria manifesto já emitido
# apontar para um arquivo que não se reproduz.
#
# ⚠️ **Yu Gothic é PROPRIETÁRIA da Microsoft**: vem no Windows 8.1+ e no macOS
# (pacote japonês), e NÃO pode ser redistribuída — não existe no Google Fonts
# nem no Fontsource, e embutir o .ttf do Windows aqui seria violação de licença,
# ainda mais num repositório PÚBLICO. Por isso ela é declarada como fonte DO
# SISTEMA e vem acompanhada da **Noto Sans JP** (livre, empacotada, ~13KB no
# subconjunto latino) para quem não a tem instalada — Android, iPhone, Linux, que
# é a maior parte do público do wizard. As duas são de origem tipográfica
# japonesa e desenho humanista, então a troca não salta aos olhos.
#
# A cadeia mora AQUI, não no front: fonte escolhida por engano quebra a tela
# inteira, e um `<select>` com valores conhecidos não tem como produzir isso
# (regra do "campo livre erra em silêncio").
FONTES = {
    "yu-gothic": {
        "rotulo": "Yu Gothic",
        "pilha": "'Yu Gothic UI', 'Yu Gothic', 'YuGothic', 'Noto Sans JP', "
                 "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "nota": "Padrão do sistema. Instalada no Windows; em celular e Linux, "
                "usa a Noto Sans JP (parecida, já embutida).",
    },
    "outfit": {
        "rotulo": "Outfit",
        "pilha": "'Outfit', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "nota": "A fonte original do sistema, geométrica e arredondada. Embutida.",
    },
    "noto-sans-jp": {
        "rotulo": "Noto Sans JP",
        "pilha": "'Noto Sans JP', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "nota": "Embutida — vale igual em qualquer aparelho, sem depender do que "
                "está instalado.",
    },
    "sistema": {
        "rotulo": "Fonte do aparelho",
        "pilha": "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', "
                 "Arial, sans-serif",
        "nota": "Cada pessoa vê a fonte padrão do próprio sistema. É a que carrega "
                "mais rápido, porque não baixa nada.",
    },
    "georgia": {
        "rotulo": "Georgia (com serifa)",
        "pilha": "Georgia, 'Times New Roman', serif",
        "nota": "Com serifa, ar mais formal. Presente em Windows, macOS e Android.",
    },
}
FONTE_PADRAO = "yu-gothic"


def pilha_da_fonte(chave: str | None) -> str:
    """A cadeia CSS de uma fonte do catálogo; chave desconhecida cai no padrão.

    Nunca levanta: uma chave inválida gravada no banco (edição manual, versão
    antiga) deixaria o sistema SEM fonte nenhuma, e o defeito apareceria como
    "a tela ficou estranha" — sem nada acusando a causa.
    """
    return FONTES.get(chave or "", FONTES[FONTE_PADRAO])["pilha"]


# Padrões históricos (o que estava chumbado). Viram só o valor inicial.
_PADRAO = {
    "empresa_nome": "Green House",
    "empresa_razao": "GREEN HOUSE SERVIÇOS DE LOCAÇÃO DE MÃO DE OBRA LTDA",
    "empresa_cnpj": "12.531.678/0001-80",
    "empresa_endereco": "SCIA Quadra 15, Conjunto 13, Lote 8, Zona Industrial (Guará), "
                        "Brasília/DF, CEP 71.250-015",
    "empresa_contato": "+55 61 3346-8812 | www.greenhousedf.com.br",
    "empresa_fonte": FONTE_PADRAO,
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
