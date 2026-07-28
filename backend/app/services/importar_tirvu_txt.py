"""Padronização em massa de cargos e jornadas colados da tela do Tirvu
(feedback de campo 2026-07-27: "tive problemas para subir cadastro em massa
para o Tirvu por conta das padronizações... tenho que fazer muita coisa
manualmente").

O RH copia a lista inteira da tela do Tirvu (Cargos ou Jornadas) e cola num
.txt. Cada registro vira uma linha com campos separados por TAB, intercalada
com "lixo" de UI (iniciais do avatar, nome do responsável, data da alteração)
em linhas próprias — sobra ao filtrar por `^\\d+\\t`.

Este módulo é PURO (sem SQLAlchemy/DB) para ser testável isoladamente: lê o
texto colado, valida a contagem contra o cabeçalho ("Lista de Cargos 111"),
limpa a sujeira conhecida das descrições de jornada, e devolve os registros
para a camada de API propor o casamento com a base (revisão humana antes de
gravar — regra da casa, nunca merge cego)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_LINHA_REGISTRO = re.compile(r"^(\d+)\t(.*)$")
_CABECALHO_TOTAL = re.compile(r"Lista de (Cargos|Jornadas)\s+(\d+)", re.IGNORECASE)
# "...16HSem vínculos" / "...16H3 vínculos" — a coluna seguinte da tela do
# Tirvu ("vínculos") veio colada sem separador no fim da descrição copiada.
_SUJEIRA_VINCULOS = re.compile(r"(?:sem|\d+)\s*v[ií]nculos?\s*$", re.IGNORECASE)


def normalizar_texto(s) -> str:
    """Minúsculo, sem acento, espaços colapsados — mesma chave de casamento
    usada em `export_tirvu.normalizar_cargo` (consistência entre os dois
    de-paras que casam por texto)."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(s or ""))
        if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def limpar_descricao_jornada(descricao: str) -> str:
    """Remove a sujeira 'Sem vínculos'/'N vínculos' colada no fim, sem
    separador, pela cópia da tela do Tirvu."""
    return _SUJEIRA_VINCULOS.sub("", descricao).strip()


@dataclass
class ContagemInvalida(Exception):
    """O cabeçalho anuncia N registros mas o texto colado trouxe outra
    quantidade — sinal de cópia parcial (feedback de campo 2026-07-27, item
    R1 do roundtable: nada garante que o RH copiou a lista inteira)."""
    esperado: int
    encontrado: int

    def __str__(self) -> str:
        return (f"O cabeçalho anuncia {self.esperado} registros, mas foram "
                f"encontrados {self.encontrado} no texto colado. Confira se a "
                "lista foi copiada inteira da tela do Tirvu.")


@dataclass
class CargoImportado:
    tirvu_id: str
    status: str          # ATIVO | INATIVO
    cargo: str
    cargo_base: str
    cbo: str


@dataclass
class JornadaImportada:
    tirvu_id: str
    descricao: str        # já limpa da sujeira de "vínculos"
    escala: str
    tratamento: str


def _total_esperado(texto: str) -> int | None:
    m = _CABECALHO_TOTAL.search(texto)
    return int(m.group(2)) if m else None


def parsear_cargos(texto: str) -> list[CargoImportado]:
    """Extrai os registros de cargo do texto colado (ID\tStatus\t\tCargo\t
    Cargo Base\tCBO\t...). Levanta ContagemInvalida se o cabeçalho anunciar
    uma contagem diferente da encontrada."""
    total_esperado = _total_esperado(texto)
    itens: list[CargoImportado] = []
    for linha in texto.splitlines():
        m = _LINHA_REGISTRO.match(linha)
        if not m:
            continue
        tirvu_id, resto = m.groups()
        partes = resto.split("\t")
        # Status vem com espaços de indentação da UI ("  ATIVO", "  INATIVO").
        status = partes[0].strip().upper() if len(partes) > 0 else ""
        cargo = partes[2].strip() if len(partes) > 2 else ""
        cargo_base = partes[3].strip() if len(partes) > 3 else ""
        cbo = partes[4].strip() if len(partes) > 4 else ""
        if not cargo:
            continue
        itens.append(CargoImportado(tirvu_id=tirvu_id, status=status,
                                    cargo=cargo, cargo_base=cargo_base, cbo=cbo))
    if total_esperado is not None and len(itens) != total_esperado:
        raise ContagemInvalida(esperado=total_esperado, encontrado=len(itens))
    return itens


def parsear_jornadas(texto: str) -> list[JornadaImportada]:
    """Extrai os registros de jornada (ID\tDescrição\tEscala\tTratamento\t...),
    limpando a sujeira de 'vínculos' colada. Levanta ContagemInvalida se a
    contagem não bater com o cabeçalho."""
    total_esperado = _total_esperado(texto)
    itens: list[JornadaImportada] = []
    for linha in texto.splitlines():
        m = _LINHA_REGISTRO.match(linha)
        if not m:
            continue
        tirvu_id, resto = m.groups()
        partes = resto.split("\t")
        descricao_bruta = partes[0].strip() if len(partes) > 0 else ""
        escala = partes[1].strip() if len(partes) > 1 else ""
        tratamento = partes[2].strip() if len(partes) > 2 else ""
        if not descricao_bruta:
            continue
        descricao = limpar_descricao_jornada(descricao_bruta)
        itens.append(JornadaImportada(tirvu_id=tirvu_id, descricao=descricao,
                                      escala=escala, tratamento=tratamento))
    if total_esperado is not None and len(itens) != total_esperado:
        raise ContagemInvalida(esperado=total_esperado, encontrado=len(itens))
    return itens


@dataclass
class GrupoHomonimo:
    """Mais de um tirvu_id ativo para o mesmo texto normalizado — o de-para por
    texto não sabe separar (feedback de campo 2026-07-27, R3 do roundtable:
    ex. 'AUXILIAR DE SERVIÇOS GERAIS' tem 514225=limpeza e 763125=produção,
    87 pessoas na base real, os dois IDs ativos). Sinaliza; NUNCA funde."""
    chave_normalizada: str
    itens: list = field(default_factory=list)  # [CargoImportado] do mesmo texto


def detectar_homonimos_cargo(itens: list[CargoImportado]) -> list[GrupoHomonimo]:
    """Agrupa cargos cujo texto normalizado colide. Só reporta os grupos com
    mais de um ID ATIVO (o RH decide) — se só um está ativo, o de-para pode
    propor esse sozinho, sem ambiguidade."""
    por_chave: dict[str, list[CargoImportado]] = {}
    for it in itens:
        por_chave.setdefault(normalizar_texto(it.cargo), []).append(it)
    grupos = []
    for chave, lista in por_chave.items():
        if len(lista) < 2:
            continue
        ativos = [c for c in lista if c.status == "ATIVO"]
        if len(ativos) >= 2:
            grupos.append(GrupoHomonimo(chave_normalizada=chave, itens=lista))
    return grupos


def detectar_duplicatas_jornada(itens: list[JornadaImportada]) -> list[GrupoHomonimo]:
    """Mesma ideia, para descrição de jornada normalizada (após limpar a
    sujeira de 'vínculos') — os pares reais nos dados de 2026-07-27 foram só 3
    de 458, mas o sistema SINALIZA, nunca funde sozinho."""
    por_chave: dict[str, list[JornadaImportada]] = {}
    for it in itens:
        por_chave.setdefault(normalizar_texto(it.descricao), []).append(it)
    return [GrupoHomonimo(chave_normalizada=chave, itens=lista)
            for chave, lista in por_chave.items() if len(lista) >= 2]
