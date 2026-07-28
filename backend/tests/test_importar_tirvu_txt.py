"""Teste unitário do parser de cargos/jornadas colados da tela do Tirvu — sem
banco (services/importar_tirvu_txt.py é puro).

Cobre o feedback de campo 2026-07-27 ("tive problemas para subir cadastro em
massa para o Tirvu por conta das padronizações"). Valida contra os dados REAIS
do RH (docs/jornadas e cargos/*.txt), quando presentes — sem eles, cobre só os
casos sintéticos (contagem, sujeira, homônimos).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_importar_tirvu_txt.py
"""

import os

from app.services.importar_tirvu_txt import (ContagemInvalida,
                                              detectar_duplicatas_jornada,
                                              detectar_homonimos_cargo,
                                              limpar_descricao_jornada,
                                              normalizar_texto, parsear_cargos,
                                              parsear_jornadas)

# ---------- Sujeira de "vínculos" colada (186 dos 458 casos reais) ----------

assert limpar_descricao_jornada("...13H - 16HSem vínculos") == "...13H - 16H"
assert limpar_descricao_jornada("...19H - 21H3 vínculos") == "...19H - 21H"
assert limpar_descricao_jornada("...19H - 21H") == "...19H - 21H"  # sem sujeira, intacto

# ---------- Contagem do cabeçalho (feedback: cópia parcial) ----------

texto_cargos_ok = "Lista de Cargos 2\nID\tStatus\t\tCargo\tCargo Base\tCBO\t\n" \
    "1\tATIVO\t\tCARGO A\tCARGO A\t100000\t\n2\tATIVO\t\tCARGO B\tCARGO B\t100001\t\n"
assert len(parsear_cargos(texto_cargos_ok)) == 2

texto_cargos_parcial = "Lista de Cargos 3\nID\tStatus\t\tCargo\tCargo Base\tCBO\t\n" \
    "1\tATIVO\t\tCARGO A\tCARGO A\t100000\t\n2\tATIVO\t\tCARGO B\tCARGO B\t100001\t\n"
try:
    parsear_cargos(texto_cargos_parcial)
    raise AssertionError("deveria ter levantado ContagemInvalida")
except ContagemInvalida as e:
    assert e.esperado == 3 and e.encontrado == 2

# Sem cabeçalho reconhecível: não valida contagem (não quebra, não bloqueia).
texto_sem_cabecalho = "1\tATIVO\t\tCARGO A\tCARGO A\t100000\t\n"
assert len(parsear_cargos(texto_sem_cabecalho)) == 1

# ---------- Homônimos: só sinaliza quando 2+ estão ATIVOS ----------

texto_homonimo_ok = (
    "Lista de Cargos 3\nID\tStatus\t\tCargo\tCargo Base\tCBO\t\n"
    "1\tATIVO\t\tAUXILIAR X\tAUXILIAR X\t111111\t\n"
    "2\tINATIVO\t\tAuxiliar X\tAuxiliar X\t222222\t\n"  # 1 inativo -> sem ambiguidade
    "3\tATIVO\t\tCARGO DIFERENTE\tCARGO DIFERENTE\t333333\t\n"
)
cargos = parsear_cargos(texto_homonimo_ok)
assert len(cargos) == 3
assert detectar_homonimos_cargo(cargos) == []  # só 1 ativo em cada grupo -> nada a decidir

texto_homonimo_ambiguo = (
    "Lista de Cargos 2\nID\tStatus\t\tCargo\tCargo Base\tCBO\t\n"
    "1\tATIVO\t\tAUXILIAR Y\tAUXILIAR Y\t111111\t\n"
    "2\tATIVO\t\tAuxiliar Y\tAuxiliar Y\t222222\t\n"  # 2 ativos, CBOs diferentes -> ambíguo
)
cargos2 = parsear_cargos(texto_homonimo_ambiguo)
grupos = detectar_homonimos_cargo(cargos2)
assert len(grupos) == 1
assert {i.tirvu_id for i in grupos[0].itens} == {"1", "2"}

# ---------- normalizar_texto: mesma regra do export_tirvu.normalizar_cargo ----------

assert normalizar_texto("Auxiliar de Serviços Gerais") == normalizar_texto("auxiliar  de servicos gerais ")

# ---------- Jornadas: duplicata só após limpar a sujeira ----------

texto_jornadas_dup = (
    "Lista de Jornadas 2\nID\tDescrição\tEscala\tTratamento\t\n"
    "1\tPOSTO X - 08H - 17HSem vínculos\tSemanal\tBANCO DE HORAS\t\n"
    "2\tPOSTO X - 08H - 17H\tSemanal\tBANCO DE HORAS\t\n"  # idêntica após limpar
)
jornadas = parsear_jornadas(texto_jornadas_dup)
assert jornadas[0].descricao == jornadas[1].descricao == "POSTO X - 08H - 17H"
dups = detectar_duplicatas_jornada(jornadas)
assert len(dups) == 1 and {i.tirvu_id for i in dups[0].itens} == {"1", "2"}

# ---------- Dados reais (se o arquivo do RH estiver presente) ----------

_CAMINHO = os.path.join(os.path.dirname(__file__), "..", "..",
                        "docs", "jornadas e cargos")
_cargos_txt = os.path.join(_CAMINHO, "cargos.txt")
_jornadas_txt = os.path.join(_CAMINHO, "jornadas.txt")

if os.path.exists(_cargos_txt) and os.path.exists(_jornadas_txt):
    with open(_cargos_txt, encoding="utf-8") as f:
        cargos_reais = parsear_cargos(f.read())
    with open(_jornadas_txt, encoding="utf-8") as f:
        jornadas_reais = parsear_jornadas(f.read())
    assert len(cargos_reais) == 111, len(cargos_reais)
    assert sum(1 for c in cargos_reais if c.status == "ATIVO") == 87
    assert len(jornadas_reais) == 458, len(jornadas_reais)
    homonimos_reais = detectar_homonimos_cargo(cargos_reais)
    # AUXILIAR DE SERVIÇOS GERAIS (87 pessoas na base real) e SUPERVISOR
    # ADMINISTRATIVO (mesmo CBO) — ver docs/planejamento/09-roadmap...md, R3.
    assert len(homonimos_reais) == 2, [g.chave_normalizada for g in homonimos_reais]
    dups_reais = detectar_duplicatas_jornada(jornadas_reais)
    assert len(dups_reais) == 3, len(dups_reais)
    print("test_importar_tirvu_txt: OK (com dados reais)")
else:
    print("test_importar_tirvu_txt: OK (arquivos reais ausentes — só casos sintéticos)")
