"""Capitalização de nome de pessoa — um lugar só.

Feedback do Bruno (2026-08-02):

> *"o candidato hora digita tudo em caixa baixa, outros tudo em caixa alta,
> outros fazem o correto... menos como no exemplo a seguir Maria De Fátima,
> onde o 'De' nesse caso deveria ser 'de'. Tem como padronizar prevendo essas
> coisas e outras mais? Está muito feio no visual do front e até nas fichas
> geradas, bem como nos e-mails."*

O `.title()` do Python é justamente o que PRODUZ o defeito reclamado:
`"maria de fátima".title()` devolve `"Maria De Fátima"`. E o sistema não só
tolerava isso — ele o gerava: `ocr_rg.py` sugeria o nome da mãe já com
`.title()`, e o candidato aceitava a sugestão. Ou seja, "Maria De Fátima" podia
ter sido escrita pelo próprio portal.

## O que esta função resolve, e o que ela deliberadamente não tenta

Resolve o comum: caixa alta, caixa baixa, preposições, iniciais separadas
("Maria D Fátima"), sufixos romanos e o `d'` de "D'Ávila". Trata "Mc"/"Mac"
e nomes com hífen ("Ana-Clara").

**Não tenta acentuar.** `FATIMA` continua `Fatima`, nunca vira `Fátima` — a
função capitaliza, não adivinha ortografia. É também por isso que a base
existente NÃO deve ser migrada em lote: o que está gravado em caixa alta perdeu
o acento na origem, e uma migração cega gravaria "Fatima" como se fosse o nome
correto da pessoa. Padronizar na ENTRADA cobre daqui para a frente sem
reescrever o nome de ninguém.

**Nunca devolve vazio para entrada não vazia**: nome é dado de identificação, e
um normalizador que "limpa" um nome esquisito até sobrar nada seria pior que o
nome esquisito.
"""

import re

# Preposições e artigos que ficam em minúscula quando NÃO são a primeira
# palavra. "Di"/"Del"/"Dello" cobrem sobrenomes italianos; "van"/"von"/"der"
# os holandeses e alemães, comuns em Brasília por causa das embaixadas.
_MINUSCULAS = {
    "de", "da", "do", "das", "dos", "e",
    "di", "del", "della", "dello", "dalla", "degli",
    "van", "von", "der", "den", "du", "la", "le", "las", "los", "y",
}

# Sufixos que são numerais romanos, não nomes: "João Paulo II". Sem isto o
# `capitalize()` devolveria "Ii".
_ROMANOS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}

# Prefixos escoceses/irlandeses cuja letra seguinte também é maiúscula.
_PREFIXOS_MC = ("mc", "mac", "o'")


def _parte(palavra: str, primeira: bool, ultima: bool) -> str:
    """Capitaliza UMA palavra, respeitando as exceções."""
    baixa = palavra.lower()

    # Numeral romano só no fim ("Neto III"), senão "Vi" de "Vitória" e o "V" de
    # um nome iniciado por V virariam algarismos.
    if ultima and not primeira and baixa in _ROMANOS:
        return baixa.upper()

    # Preposição fica minúscula, exceto abrindo o nome ("Da Silva Júnior" quem
    # se chama assim de primeiro nome existe, e "de" sozinho no começo é erro
    # de digitação mais provável que sobrenome).
    if baixa in _MINUSCULAS and not primeira:
        return baixa

    # d'Ávila / D'Ávila: o apóstrofo separa e a letra seguinte é maiúscula.
    if "'" in baixa:
        pre, _, resto = baixa.partition("'")
        if pre in ("d", "o", "l") and resto:
            # "d'Ávila" com d minúsculo é a grafia usual no meio do nome;
            # abrindo o nome, maiúsculo.
            inicial = pre.upper() if (primeira or pre != "d") else pre
            return f"{inicial}'{resto[:1].upper()}{resto[1:]}"

    # McDonald / MacEdo / O'Brien
    for pref in _PREFIXOS_MC:
        if baixa.startswith(pref) and len(baixa) > len(pref):
            resto = baixa[len(pref):]
            return f"{pref.capitalize()}{resto[:1].upper()}{resto[1:]}"

    # Hífen: cada lado capitaliza ("Ana-Clara", "Guimarães-Rosa").
    if "-" in baixa:
        return "-".join(p[:1].upper() + p[1:] if p else p for p in baixa.split("-"))

    # Inicial solta ("Maria D Fátima" → "Maria D. Fátima" fica a cargo de quem
    # digitou; aqui só se garante a maiúscula).
    return baixa[:1].upper() + baixa[1:]


def capitalizar_nome(texto: str | None) -> str:
    """`MARIA DE FÁTIMA` / `maria de fátima` → `Maria de Fátima`.

    Idempotente: aplicar duas vezes dá o mesmo resultado — importante porque o
    wizard salva a mesma seção a cada 900ms de digitação.
    """
    if not texto:
        return ""
    # Colapsa espaços repetidos sem perder o conteúdo.
    palavras = [p for p in re.split(r"\s+", texto.strip()) if p]
    if not palavras:
        return ""
    ultimo = len(palavras) - 1
    return " ".join(
        _parte(p, primeira=(i == 0), ultima=(i == ultimo))
        for i, p in enumerate(palavras)
    )


def primeiro_nome(texto: str | None) -> str:
    """Primeiro nome já capitalizado — para tratamento em e-mail.

    Existe porque ~20 pontos do sistema faziam `nome.split()[0].title()`, que
    funciona por acidente (uma palavra só) e erra em "D'Ávila".
    """
    nome = capitalizar_nome(texto)
    return nome.split(" ")[0] if nome else ""
