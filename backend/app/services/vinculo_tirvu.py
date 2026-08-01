"""Vincular colaboradores a posto, cargo e jornada a partir da planilha do
Tirvu — em massa, com conferência antes (v2.39).

Pedido do Bruno em 2026-08-01: *"precisa vincular os colaboradores em massa
também a seus respectivos postos, cargos e jornadas, conforme Tirvu, quero
evitar trabalho manual"*.

A planilha de Colaboradores do Tirvu traz, por pessoa, `Lotação`, `Cargo`,
`Jornada de Trabalho` e `PCD?` — e o portal só usava as duas primeiras. Medido
contra os dados reais de 1.156 pessoas: **cargo casa em 100%**, **jornada em
99%** e **posto em 11%** (a lotação vem abreviada, "ANAC" para
"ANAC - 14/2026 - AEROPORTO" ou "- SEDE": ambiguidade real, que fica para o
de-para assistido).

Três regras que sustentam este módulo:

1. **Nada é gravado sem conferência.** `analisar` só LÊ e classifica; quem
   grava é a rota, com a lista que o RH confirmou. É a mesma mecânica da
   Incidência de Benefícios.
2. **Divergência não é preenchimento.** Campo vazio no portal → o Tirvu manda.
   Campo com valor DIFERENTE → fica separado, porque pode ser correção feita
   aqui à mão, e sobrescrever 1.000 registros é irreversível na prática.
3. **O que não casa aparece com nome e motivo.** Jornada sem par, posto sem
   par e CPF fora da base viram lista, nunca silêncio — a lição do lote de
   documento crítico.

O cargo NÃO precisa de vínculo por pessoa: `cargo_funcao` é texto livre e o
export resolve o ID pelo de-para (`CargoTirvu`, alimentado pela v2.38). Aqui
ele só é preenchido quando está vazio no portal.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


def normalizar(texto) -> str:
    """Minúsculo, sem acento, espaços colapsados — a mesma chave de casamento
    usada no de-para de cargos e na importação de jornadas."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(t.split()).strip().lower()


def so_digitos(v) -> str:
    return "".join(ch for ch in str(v or "") if ch.isdigit())


# Situação de cada campo, por pessoa. O nome é o que a tela mostra.
PREENCHER = "preencher"     # está vazio no portal e o Tirvu tem o valor
DIVERGE = "diverge"         # portal e Tirvu discordam — decisão humana
IGUAL = "igual"             # nada a fazer
SEM_PAR = "sem_par"         # o valor do Tirvu não existe no portal
VAZIO = "vazio"             # o Tirvu não informou


@dataclass
class Decisao:
    """O que se propõe para UMA pessoa."""

    cpf: str
    nome: str
    achou_cadastro: bool = False
    # jornada
    jornada_texto: str = ""
    jornada_id: str | None = None      # id da Jornada casada no portal
    jornada_situacao: str = VAZIO
    jornada_atual: str = ""            # descrição do que está gravado hoje
    # cargo (texto livre; o ID sai do de-para no export)
    cargo_texto: str = ""
    cargo_situacao: str = VAZIO
    cargo_atual: str = ""
    # posto
    lotacao_texto: str = ""
    posto_id: str | None = None
    posto_situacao: str = VAZIO
    posto_atual: str = ""
    # PCD (dado sensível de saúde: só é PROPOSTO, nunca aplicado em silêncio)
    pcd: bool | None = None
    pcd_deficiencia: str = ""
    pcd_situacao: str = VAZIO

    def tem_proposta(self) -> bool:
        """Há algo a aplicar sem decisão humana?"""
        return PREENCHER in (self.jornada_situacao, self.cargo_situacao,
                             self.posto_situacao, self.pcd_situacao)

    def tem_divergencia(self) -> bool:
        return DIVERGE in (self.jornada_situacao, self.cargo_situacao,
                           self.posto_situacao, self.pcd_situacao)


@dataclass
class Analise:
    decisoes: list[Decisao] = field(default_factory=list)
    sem_cpf: int = 0
    # Descrições do Tirvu que não existem no portal — a fila do que falta
    # importar/cadastrar, com quantas pessoas dependem de cada uma.
    jornadas_sem_par: dict = field(default_factory=dict)
    lotacoes_sem_par: dict = field(default_factory=dict)

    @property
    def fora_da_base(self) -> list[Decisao]:
        return [d for d in self.decisoes if not d.achou_cadastro]

    @property
    def prontas(self) -> list[Decisao]:
        return [d for d in self.decisoes if d.achou_cadastro and d.tem_proposta()
                and not d.tem_divergencia()]

    @property
    def divergentes(self) -> list[Decisao]:
        return [d for d in self.decisoes if d.achou_cadastro and d.tem_divergencia()]


def _situacao(valor_tirvu: str, casado, atual) -> str:
    """Classifica UM campo. `casado` é o que o Tirvu propõe (já resolvido
    contra a base); `atual` é o que está gravado no portal."""
    if not valor_tirvu:
        return VAZIO
    if casado is None:
        return SEM_PAR
    if atual in (None, "", []):
        return PREENCHER
    return IGUAL if str(atual) == str(casado) else DIVERGE


def analisar(linhas: list[list], *, candidatos_por_cpf: dict,
             jornadas_por_descricao: dict, postos_por_nome: dict) -> Analise:
    """Cruza a planilha com a base e devolve o que SE PROPÕE, sem gravar nada.

    `candidatos_por_cpf`: {cpf_digitos: objeto com .nome_completo, .jornada_id,
    .cargo_funcao, .posto_servico_id, .pcd (ou None)}. Os outros dois mapas são
    {chave_normalizada: id}. Passar mapas prontos (e não a sessão) mantém este
    módulo puro e obriga o chamador a carregar tudo em LOTE — com 1.156
    pessoas, uma consulta por linha seria a diferença entre segundos e minutos.
    """
    if not linhas:
        return Analise()

    cab = [normalizar(c) for c in linhas[0]]

    def col(*nomes) -> int | None:
        for n in nomes:
            if n in cab:
                return cab.index(n)
        return None

    i_cpf = col("cpf")
    i_nome = col("colaborador", "nome")
    i_jornada = col("jornada de trabalho", "jornada")
    i_cargo = col("cargo")
    i_lotacao = col("lotacao")
    i_pcd = col("pcd?", "pcd")
    i_defic = col("deficiencia")
    if i_cpf is None:
        raise ValueError("sem_coluna_cpf")

    analise = Analise()
    for bruta in linhas[1:]:
        if bruta is None or all(v in (None, "") for v in bruta):
            continue
        val = lambda i: ("" if i is None or i >= len(bruta) or bruta[i] is None  # noqa: E731
                         else str(bruta[i]).strip())
        cpf = so_digitos(val(i_cpf))
        # 11 dígitos NÃO basta: "000.000.000-00" tem onze e é lixo de cadastro.
        # Sem esta guarda, a linha vira "pessoa que não está no portal" — um
        # número inflado numa tela que o RH usa para decidir, e a causa (CPF
        # inválido na origem) fica invisível.
        if len(cpf) != 11 or len(set(cpf)) == 1:
            analise.sem_cpf += 1
            continue

        pessoa = candidatos_por_cpf.get(cpf)
        d = Decisao(cpf=cpf, nome=val(i_nome), achou_cadastro=pessoa is not None)

        d.jornada_texto = val(i_jornada)
        casada = jornadas_por_descricao.get(normalizar(d.jornada_texto)) if d.jornada_texto else None
        d.jornada_id = str(casada) if casada else None
        d.cargo_texto = val(i_cargo)
        d.lotacao_texto = val(i_lotacao)
        casado_posto = postos_por_nome.get(normalizar(d.lotacao_texto)) if d.lotacao_texto else None
        d.posto_id = str(casado_posto) if casado_posto else None

        bruto_pcd = normalizar(val(i_pcd))
        d.pcd = True if bruto_pcd == "sim" else False if bruto_pcd in ("nao", "n") else None
        d.pcd_deficiencia = val(i_defic)

        if pessoa is not None:
            d.jornada_atual = str(getattr(pessoa, "jornada_id", "") or "")
            d.cargo_atual = getattr(pessoa, "cargo_funcao", "") or ""
            d.posto_atual = str(getattr(pessoa, "posto_servico_id", "") or "")
            d.jornada_situacao = _situacao(d.jornada_texto, d.jornada_id, d.jornada_atual)
            # Cargo casa por TEXTO normalizado: "Auxiliar"/"AUXILIAR" são o
            # mesmo cargo e não podem virar divergência de gente para conferir.
            cargo_casado = d.cargo_texto or None
            atual_cargo = d.cargo_atual
            if cargo_casado and atual_cargo and normalizar(cargo_casado) == normalizar(atual_cargo):
                d.cargo_situacao = IGUAL
            else:
                d.cargo_situacao = _situacao(d.cargo_texto, cargo_casado, atual_cargo)
            d.posto_situacao = _situacao(d.lotacao_texto, d.posto_id, d.posto_atual)
            atual_pcd = getattr(pessoa, "pcd", None)
            if d.pcd is None:
                d.pcd_situacao = VAZIO
            elif atual_pcd is None:
                d.pcd_situacao = PREENCHER
            else:
                d.pcd_situacao = IGUAL if bool(atual_pcd) == d.pcd else DIVERGE

        # Filas do que não existe na base — com quantas pessoas dependem.
        if d.jornada_texto and d.jornada_id is None:
            analise.jornadas_sem_par[d.jornada_texto] = \
                analise.jornadas_sem_par.get(d.jornada_texto, 0) + 1
        if d.lotacao_texto and d.posto_id is None:
            analise.lotacoes_sem_par[d.lotacao_texto] = \
                analise.lotacoes_sem_par.get(d.lotacao_texto, 0) + 1

        analise.decisoes.append(d)
    return analise
