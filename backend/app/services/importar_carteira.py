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

    def resumo(self) -> dict:
        return {
            "processos_novos": self.processos_novos,
            "processos_alterados": self.processos_alterados,
            "funcoes_novas": self.funcoes_novas,
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


def analisar(abas: dict[str, list[list[str]]], db: Session) -> Previa:
    """Lê as abas e devolve o que entraria — sem gravar nada."""
    p = Previa()
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

    def funcao_de(nome: str) -> FuncaoRH:
        chave = normalizar(nome)
        if chave not in funcoes:
            # A função nasce com a PESSOA preenchida com o próprio nome da
            # planilha: ali as colunas trazem pessoas ("Fátima Sampaio"), e é o
            # que o Bruno ajusta depois na tela, dizendo qual é o cargo dela.
            # Nascer vazia faria a carteira importada parecer inteira sem dono.
            f = FuncaoRH(nome=nome.strip()[:120], pessoa_nome=nome.strip()[:200],
                         ordem=len(funcoes))
            db.add(f)
            db.flush()
            funcoes[chave] = f
        return funcoes[chave]

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
