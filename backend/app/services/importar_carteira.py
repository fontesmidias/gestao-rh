"""Importa a Carteira de Processos do RH a partir da planilha do Bruno (v2.91).

Lê `Carteira_Processos_RH_MatrizRACI.xlsx`: as abas **Matriz C1** e **Matriz
C2** (uma linha por processo, colunas de titular e apoios) e a **Legenda e
Regras** (a equipe e o que cada função é).

Como todas as importações desta casa, **PROPÕE e não grava**: devolve o que
entraria, o que mudaria e o que não casou, e só o `aplicar` escreve — a mesma
mecânica da Incidência de Benefícios e do de-para do Tirvu. O motivo é o mesmo
de sempre: a planilha é digitada à mão, e merge cego cria associação errada
que ninguém percebe.

Reusa o `_ler_abas` de `incidencia_beneficios.py` (zip + XML puro) em vez do
openpyxl: as planilhas que circulam aqui quebram o openpyxl com stylesheet
inválido, e este leitor já é o padrão do projeto para multi-abas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.processo import AtribuicaoProcesso, FuncaoRH, Processo
from app.services.processos import CENARIOS, normalizar

# O cabeçalho real da planilha (linha 4 das abas Matriz).
COL_ID = "id"
COL_FASE = "fase"
COL_PROCESSO = "processo"
COL_RITMO = "ritmo"
COL_TITULAR = "titular"


@dataclass
class Previa:
    processos_novos: list[dict] = field(default_factory=list)
    processos_alterados: list[dict] = field(default_factory=list)
    funcoes_novas: list[str] = field(default_factory=list)
    # Linhas que o parser não conseguiu usar, COM o motivo. Nunca descartadas
    # em silêncio: importação que "funciona" e ignora 8 linhas é pior que uma
    # que falha, porque ninguém confere o que não foi avisado.
    ignoradas: list[dict] = field(default_factory=list)
    cenarios: list[str] = field(default_factory=list)
    # {chave_normalizada: {"pessoa", "funcao"}} — vem da aba "Legenda e Regras".
    equipe: dict = field(default_factory=dict)

    def resumo(self) -> dict:
        return {
            "processos_novos": self.processos_novos,
            "processos_alterados": self.processos_alterados,
            # Mostra "Pessoa (Função)" quando a legenda tem o par: quem
            # confere a importação precisa ver que vai entrar um CARGO.
            "funcoes_novas": [
                (f"{n} — {self.equipe[k]['funcao']}"
                 if (k := normalizar(n)) in self.equipe else n)
                for n in self.funcoes_novas],
            "ignoradas": self.ignoradas,
            "cenarios": self.cenarios,
            "total": len(self.processos_novos) + len(self.processos_alterados),
        }


def _cabecalho(linhas: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Acha a linha de cabeçalho e mapeia coluna → índice.

    Procurada, não chumbada na linha 4: a planilha ganha linhas de título com o
    tempo, e um índice fixo quebraria calado — lendo "Equipe atual:" como se
    fosse um processo.
    """
    for i, linha in enumerate(linhas[:15]):
        celulas = [normalizar(c) for c in linha]
        if COL_ID in celulas and COL_PROCESSO in celulas:
            mapa: dict[str, int] = {}
            for j, c in enumerate(celulas):
                if c:
                    mapa[c] = j
            return i, mapa
    raise ValueError("cabecalho_nao_encontrado")


def _coluna(mapa: dict[str, int], comeca_com: str) -> int | None:
    """Índice da coluna cujo nome COMEÇA com o termo.

    Casamento por prefixo, não por igualdade: a coluna do titular se chama
    "Titular (Dono)" na planilha, e procurar por "titular" exato a deixava de
    fora — a cadeia começava no 2º apoio e o processo aparecia com o titular
    errado, sem erro nenhum. Defeito silencioso: a importação "funcionava".
    """
    for nome, idx in mapa.items():
        if nome.startswith(comeca_com):
            return idx
    return None


def _colunas_de_apoio(mapa: dict[str, int]) -> list[int]:
    """Índices das colunas de apoio, na ORDEM da cadeia (2º, 3º, 4º…).

    Vêm do cabeçalho ("2º Apoio", "3º Apoio"…) e não de um intervalo fixo: o
    C2 tem uma coluna a mais que o C1, e chumbar o intervalo faria o último
    apoio sumir — justamente o elo de quem cobre em última instância.
    """
    achados = []
    for nome, idx in mapa.items():
        if "apoio" in nome:
            digitos = "".join(c for c in nome if c.isdigit())
            achados.append((int(digitos) if digitos else 99, idx))
    return [idx for _, idx in sorted(achados)]


def equipe_da_legenda(abas: dict[str, list[list[str]]]) -> dict[str, dict]:
    """Pessoa → função, lido da aba "Legenda e Regras" (v2.91.1).

    As colunas das abas Matriz trazem **pessoas** ("Fátima Sampaio"), não
    funções. Sem esta leitura, a carteira importada mostrava "Fátima Sampaio"
    na coluna FUNÇÃO — e o módulo inteiro se apoia em *"a titularidade
    acompanha a função, não a pessoa"*. Com a função nomeada como pessoa, a
    promessa não se cumpre: trocar quem ocupa o cargo exigiria renomear a
    própria função, que é exatamente o trabalho que o módulo existe para evitar.

    A aba tem o par pronto: `Bruno Fontes | Coordenação / Gestão de RH | C1 e C2`.
    """
    equipe: dict[str, dict] = {}
    for aba, linhas in abas.items():
        if "legenda" not in normalizar(aba):
            continue
        dentro = False
        for linha in linhas:
            celulas = [(c or "").strip() for c in linha]
            primeira = celulas[0] if celulas else ""
            # A seção começa em "EQUIPE" e termina no próximo título em caixa
            # alta (RITMO, REGRAS). Delimitar assim, e não por intervalo de
            # linhas, porque a planilha ganha seções com o tempo.
            if normalizar(primeira) == "equipe":
                dentro = True
                continue
            if dentro and primeira.isupper() and len(primeira) > 3:
                break
            if not dentro or not primeira:
                continue
            funcao = celulas[1] if len(celulas) > 1 else ""
            if funcao:
                equipe[normalizar(primeira)] = {"pessoa": primeira, "funcao": funcao}
    return equipe


def analisar(abas: dict[str, list[list[str]]], db: Session) -> Previa:
    """Lê as abas e devolve o que entraria — sem gravar nada."""
    p = Previa()
    # Pessoa → função, da aba de legenda. É o que faz a coluna FUNÇÃO mostrar
    # "Assistente de RH Júnior" em vez de repetir o nome da pessoa (v2.91.1).
    p.equipe = equipe_da_legenda(abas)
    existentes = {x.codigo: x for x in db.scalars(select(Processo)).all()}
    funcoes = {normalizar(f.nome): f.nome
               for f in db.scalars(select(FuncaoRH)).all()}
    vistas: set[str] = set()

    for aba, linhas in abas.items():
        chave = normalizar(aba)
        if "matriz" not in chave:
            continue
        cenario = "C2" if "c2" in chave else "C1"
        p.cenarios.append(cenario)

        try:
            inicio, mapa = _cabecalho(linhas)
        except ValueError:
            p.ignoradas.append({"aba": aba, "linha": None,
                                "motivo": "cabeçalho (ID/Processo) não encontrado"})
            continue
        apoios = _colunas_de_apoio(mapa)

        for n, linha in enumerate(linhas[inicio + 1:], start=inicio + 2):
            def celula(idx: int | None) -> str:
                if idx is None or idx >= len(linha):
                    return ""
                return (linha[idx] or "").strip()

            codigo = celula(_coluna(mapa, COL_ID))
            nome = celula(_coluna(mapa, COL_PROCESSO))
            # Linha de rodapé, separador ou título solto: sem código E sem
            # nome não é processo. Só vira "ignorada" quando tem UM dos dois —
            # aí é linha pela metade, e o RH precisa saber.
            if not codigo and not nome:
                continue
            if not codigo or not nome:
                p.ignoradas.append({
                    "aba": aba, "linha": n,
                    "motivo": "sem código" if not codigo else "sem nome do processo"})
                continue

            titular = celula(_coluna(mapa, COL_TITULAR))
            cadeia = [titular] + [celula(i) for i in apoios]
            cadeia = [c for c in cadeia if c]
            if not cadeia:
                p.ignoradas.append({"aba": aba, "linha": n, "codigo": codigo,
                                    "motivo": "nenhum responsável na linha"})
                continue

            for pessoa in cadeia:
                if normalizar(pessoa) not in funcoes and pessoa not in p.funcoes_novas:
                    p.funcoes_novas.append(pessoa)

            item = {"codigo": codigo, "fase": celula(_coluna(mapa, COL_FASE)),
                    "nome": nome, "ritmo": celula(_coluna(mapa, COL_RITMO)),
                    "cenario": cenario, "cadeia": cadeia}

            if codigo in existentes:
                atual = existentes[codigo]
                if (atual.nome != nome or (atual.ritmo or "") != item["ritmo"]
                        or (atual.fase or "") != item["fase"]):
                    item["antes"] = {"nome": atual.nome, "ritmo": atual.ritmo,
                                     "fase": atual.fase}
                p.processos_alterados.append(item)
            elif codigo in vistas:
                # O mesmo processo aparece no C1 E no C2 — é o normal, não é
                # duplicata: cada aba descreve a cadeia de um cenário.
                p.processos_alterados.append(item)
            else:
                p.processos_novos.append(item)
            vistas.add(codigo)

    return p


def aplicar(db: Session, previa: Previa) -> dict:
    """Grava o que a prévia mostrou. Idempotente: reimportar ATUALIZA."""
    funcoes = {normalizar(f.nome): f for f in db.scalars(select(FuncaoRH)).all()}
    # Índice auxiliar por PESSOA: as colunas da Matriz trazem pessoas, e é por
    # elas que se acha a função já criada numa importação anterior.
    por_pessoa = {normalizar(f.pessoa_nome): f
                  for f in funcoes.values() if (f.pessoa_nome or "").strip()}

    def funcao_de(nome: str) -> FuncaoRH:
        """A função de quem está escrito na célula da Matriz.

        A célula traz a PESSOA; o nome da FUNÇÃO vem da aba de legenda. Sem
        isso, a coluna "Função" da tela repetia o nome da pessoa — e o módulo
        se apoia justamente em titularidade por CARGO: com a função chamada
        "Fátima Sampaio", trocar quem ocupa o cargo exigiria renomear a função.
        Sem par na legenda (nome que só aparece na Matriz), cai no próprio
        nome — melhor uma função com nome provisório, que o RH renomeia na
        tela, do que perder a linha.
        """
        chave = normalizar(nome)
        par = previa.equipe.get(chave)
        rotulo = (par or {}).get("funcao") or nome
        pessoa = (par or {}).get("pessoa") or nome

        existente = funcoes.get(normalizar(rotulo)) or por_pessoa.get(chave)
        if existente is not None:
            # Reimportar não recria: atualiza o rótulo se a legenda mudou.
            if par and existente.nome != rotulo.strip()[:120]:
                existente.nome = rotulo.strip()[:120]
            return existente

        f = FuncaoRH(nome=rotulo.strip()[:120], pessoa_nome=pessoa.strip()[:200],
                     ordem=len(funcoes))
        db.add(f)
        db.flush()
        funcoes[normalizar(f.nome)] = f
        por_pessoa[normalizar(pessoa)] = f
        return f

    criados = atualizados = vinculos = 0
    for item in previa.processos_novos + previa.processos_alterados:
        p = db.scalar(select(Processo).where(Processo.codigo == item["codigo"]))
        if p is None:
            p = Processo(codigo=item["codigo"], nome=item["nome"],
                         fase=item["fase"] or "—", ritmo=item["ritmo"] or None,
                         ordem=criados)
            db.add(p)
            db.flush()
            criados += 1
        else:
            p.nome = item["nome"]
            p.fase = item["fase"] or p.fase
            p.ritmo = item["ritmo"] or p.ritmo
            atualizados += 1

        # A cadeia é REESCRITA por (processo, cenário): a planilha é a fonte, e
        # manter posições antigas ao lado das novas produziria uma cadeia com
        # dois "2º apoio" — o `UniqueConstraint` recusaria, e o import morreria
        # no meio de um lote parcialmente aplicado.
        for velha in db.scalars(select(AtribuicaoProcesso).where(
                AtribuicaoProcesso.processo_id == p.id,
                AtribuicaoProcesso.cenario == item["cenario"])).all():
            db.delete(velha)
        db.flush()

        for pos, nome in enumerate(item["cadeia"], start=1):
            db.add(AtribuicaoProcesso(processo_id=p.id, funcao_id=funcao_de(nome).id,
                                      cenario=item["cenario"], posicao=pos))
            vinculos += 1

    return {"criados": criados, "atualizados": atualizados,
            "vinculos": vinculos, "funcoes": len(funcoes),
            "ignoradas": len(previa.ignoradas)}


def escala_da_planilha(abas: dict[str, list[list[str]]]) -> list[dict]:
    """Lê a aba "Escala Diária": quem atende cada canal em cada dia (v2.91.1).

    A aba é uma sequência de blocos — um cabeçalho de cenário, depois "Semana
    N" com uma linha por dia útil e uma coluna por posto (Demandas, E-mail,
    Teams, WhatsApp, Retaguarda). Os POSTOS vêm da linha "Dia | ..." de cada
    bloco, não de uma lista fixa aqui: o Bruno pode acrescentar um canal, e uma
    lista chumbada o descartaria em silêncio.
    """
    itens: list[dict] = []
    for aba, linhas in abas.items():
        if "escala" not in normalizar(aba):
            continue
        cenario, semana, postos = "C1", 0, []
        for linha in linhas:
            celulas = [(c or "").strip() for c in linha]
            primeira = celulas[0] if celulas else ""
            chave = normalizar(primeira)
            if chave.startswith("cenario"):
                # "Cenário 2 — Projeção com a Analista…" → C2
                cenario = "C2" if "2" in primeira.split("—")[0] else "C1"
                continue
            if chave.startswith("semana"):
                digitos = "".join(c for c in primeira if c.isdigit())
                semana = int(digitos) if digitos else semana + 1
                continue
            if chave == "dia":
                postos = [c for c in celulas[1:] if c]
                continue
            if not postos or not primeira or not semana:
                continue
            for i, posto in enumerate(postos, start=1):
                pessoa = celulas[i] if i < len(celulas) else ""
                if pessoa:
                    itens.append({"cenario": cenario, "semana": semana,
                                  "dia": primeira, "posto": posto,
                                  "pessoa": pessoa})
    return itens


def aplicar_escala(db: Session, itens: list[dict]) -> int:
    """Reescreve a escala. Substituir é o certo: a planilha é a fonte, e manter
    linhas antigas ao lado das novas deixaria dois nomes no mesmo posto do mesmo
    dia — a pergunta "quem está no WhatsApp hoje?" com duas respostas."""
    from app.models.processo import EscalaCanal

    for velha in db.scalars(select(EscalaCanal)).all():
        db.delete(velha)
    db.flush()
    for i in itens:
        db.add(EscalaCanal(**i))
    return len(itens)
