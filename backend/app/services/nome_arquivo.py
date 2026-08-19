"""O nome dos arquivos que o RH baixa — um lugar só.

Padrão cravado pelo Bruno (18/08/2026), como regra para os módulos existentes e
os vindouros:

> *"Para todos os documentos que for baixar, como regra para os módulos
> existentes e os vindouros, padronizar como matrícula - nome do colaborador -
> nome do documento. Tudo em caixa alta e sem caracteres especiais, matrícula
> com seis dígitos no padrão 000000"*

É a continuação do pedido de 2026-08-12, que gerou o `nome_arquivo_dossie()`
(`DOCS ADM - KATIA POLIANE`). Aquele resolveu UM documento; este resolve a regra
— havia **quatro funções de nomeação diferentes** e 31 pontos montando nome à
mão, cada um com seu padrão.

**Por que caixa alta e sem acento** (não é estética): o header HTTP
`Content-Disposition` só carrega ASCII com segurança — nome acentuado chega
truncado ou codificado em alguns clientes —, e a pasta física do RH é toda em
caixa alta.

⚠️ **O front precisa passar o mesmo nome.** O `BotaoBaixar.jsx` cria um
`objectURL` e o `Content-Disposition` da rota NÃO o alcança: o nome vem do prop
`nome` no JSX. Padronizar só aqui deixaria metade dos downloads com o padrão
antigo — e a metade errada seria justo a das rotas autenticadas.
"""

from __future__ import annotations

import unicodedata

# Nomes de arquivo reservados no Windows: usados sozinhos, o arquivo não pode
# ser criado. Mesma lista do `export_planilha.slug()`.
_RESERVADOS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def limpar(texto: str | None) -> str:
    """Caixa alta, sem acento, sem caractere proibido — pronto para o header.

    Barra e dois-pontos viram caminho ou stream alternativo no Windows; hífen
    some porque é o SEPARADOR do padrão, e um hífen dentro do nome da pessoa
    faria "MARIA-JOSE" parecer dois campos.
    """
    limpo = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    for proibido in '\\/:*?"<>|-':
        limpo = limpo.replace(proibido, " ")
    return " ".join(limpo.split()).upper()


def montar(matricula: str | None, pessoa: str | None, documento: str | None,
           extensao: str = "pdf") -> str:
    """`000123 - MARIA DE FATIMA - FICHA DE ADMISSAO.pdf`.

    As partes VAZIAS são omitidas junto com o separador — em admissão a
    matrícula quase sempre não existe (ela nasce no export para o Tirvu), e um
    arquivo chamado ` - MARIA - FICHA.pdf` teria um separador solto na frente,
    que alguns sistemas de arquivo tratam mal e todo mundo lê como erro.

    Se nada sobrar (sem matrícula, sem nome, sem documento), devolve `DOCUMENTO`
    em vez de uma string vazia: arquivo sem nome não pode ser salvo.
    """
    from app.services.export_tirvu import matricula_formatada

    partes = [
        matricula_formatada(matricula),
        limpar(pessoa),
        limpar(documento),
    ]
    base = " - ".join(p for p in partes if p) or "DOCUMENTO"
    if base.upper() in _RESERVADOS:
        base = f"{base} ARQUIVO"
    ext = (extensao or "").lstrip(".").lower()
    return f"{base}.{ext}" if ext else base


def do_colaborador(colaborador, documento: str, extensao: str = "pdf") -> str:
    """O padrão a partir do registro da pessoa — o caso mais comum.

    Aceita qualquer objeto com `matricula` e `nome_completo`, para servir tanto
    ao `Candidato` quanto ao que vier depois.
    """
    return montar(getattr(colaborador, "matricula", None),
                  getattr(colaborador, "nome_completo", None),
                  documento, extensao)
