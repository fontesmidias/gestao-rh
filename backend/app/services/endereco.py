"""Endereço em texto — um lugar só para montar a linha que vai ao documento.

O endereço mora no banco em DOIS formatos, e essa é a origem do defeito que
motivou este módulo (feedback de campo 2026-08-01, "no Termo de Opção de VT
está vindo apenas a cidade, estado e cep"):

* **legado** — `logradouro_numero_complemento`, uma string só, de quem
  preencheu a ficha antes da leva do Tirvu;
* **atual** — `logradouro`, `numero` e `complemento` separados, porque é assim
  que o layout de importação do Tirvu exige.

Quem preenche hoje grava o formato ATUAL e deixa o legado **nulo** — nada
sincroniza os dois. Então todo documento que lia só o campo legado imprimia um
traço no lugar da rua: o Termo de VT (que declara "resido no endereço acima
informado"), a ficha de emergência, a ficha cadastral do terceirizado e o
ofício de apresentação à Presidência, onde virava uma linha de pontinhos.

A regra é a mesma dos dois formatos de data do creche (v2.27): **leia os dois**,
nunca migre em lote. Aqui não há sequer ambiguidade a resolver — só ordem de
preferência: o formato atual manda, o legado atende quem é antigo.
"""

from app.models.ficha import Endereco


def _juntar(*partes: str | None) -> str:
    return ", ".join(p.strip() for p in partes if p and str(p).strip())


def cep_formatado(cep: str | None) -> str | None:
    """CEP com hífen (00000-000) para o documento que a pessoa lê.

    No banco o campo tem 8 caracteres e guarda só os dígitos — o que está certo
    para armazenar e errado para imprimir: "CEP 72215342" num documento
    assinado parece dado sujo. Reusa a mesma regra do export do Tirvu
    (`cep_mascarado`), inclusive a de devolver o valor como veio quando não são
    8 dígitos: não é papel do formatador julgar o dado.
    """
    from app.services.export_tirvu import cep_mascarado
    return cep_mascarado(cep) or None if cep else None


def rua(e: Endereco | None) -> str | None:
    """Logradouro, número e complemento numa linha — sem bairro/cidade/CEP.

    Para os documentos que já imprimem bairro, cidade e CEP em campos
    separados; devolve `None` quando não há endereço, para o chamador decidir
    o que mostrar no lugar.
    """
    if e is None:
        return None
    if e.logradouro:
        return _juntar(e.logradouro, e.numero, e.complemento) or None
    return (e.logradouro_numero_complemento or "").strip() or None


def completo(e: Endereco | None) -> str | None:
    """O endereço inteiro em uma linha: rua, nº, complemento, bairro,
    cidade/UF — CEP.

    Para texto corrido ("residente e domiciliado à …") e para o Termo de VT,
    onde o endereço é o objeto da declaração e sair pela metade descaracteriza
    o documento.

    Partes ausentes são OMITIDAS em vez de virarem traço: "Rua X, 123,
    Ceilândia, Brasília/DF" é uma frase; "Rua X, 123, -, Brasília/DF" parece
    defeito.
    """
    if e is None:
        return None
    local = "/".join(p for p in (e.cidade, e.uf) if p)
    texto = _juntar(rua(e), e.bairro, local or None)
    cep = cep_formatado(e.cep)
    if cep:
        texto = f"{texto} — CEP {cep}" if texto else f"CEP {cep}"
    return texto or None
