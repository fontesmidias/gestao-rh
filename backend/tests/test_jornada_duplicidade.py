"""Duplicidade de jornadas: o que MERECE os olhos do RH (v2.12).

O Bruno pediu ação em massa na tela de duplicidades — 325 pares, um clique
cada. Antes de construir, medimos a fila contra os dados REAIS (planilha de
escalas de 07/2026, 269 jornadas distintas). O resultado matou o pedido:

    199 pares suspeitos, dos quais 3 eram duplicata. 99% de ruído.

Resolver 199 "em massa" seria exatamente o merge cego que este módulo existe
para impedir — e o estrago é invisível: jornada errada não dá erro, a pessoa
descobre no contracheque.

O ruído tinha causa estrutural, não de limiar:
  - 80 pares eram o MESMO texto com HORÁRIO diferente ("13H -16H" x "13H -17H");
  - 40 pares eram o MESMO horário com CLIENTE diferente (INEP x MME).

Daí as duas regras testadas aqui: número diferente ⇒ jornada diferente; mesmo
número com letras diferentes ⇒ clientes diferentes. Sobra a mesma jornada
escrita de dois jeitos, que é o que o RH precisa decidir.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_jornada_duplicidade.py
"""

from app.services.jornada_duplicidade import suspeitas

# ------------------------------------------------ casos reais da planilha
# (1) horário diferente => jornadas DIFERENTES, nunca suspeitas
assert suspeitas([
    "INTERMITENTE APOIO ADM - 2ª A 6ª - 07H - 12H - 13H -16H",
    "INTERMITENTE APOIO ADM - 2ª A 6ª - 07H - 12H - 13H -17H",
]) == [], "horário diferente (16h x 17h) não pode ser tratado como duplicata"

assert suspeitas([
    "GHS SEDE - 2ª A 5ª - 08H - 12H - 13H - 18H",
    "GHS SEDE - 2ª A 5ª - 09H - 12H - 13H - 18H",
]) == [], "uma hora a mais de entrada é outra jornada"

# (2) mesmo horário, cliente/posto diferente => DIFERENTES
for a, b in (
    ("CARLTON CENTER - ASG - 2ª A 6ª - 07H - 11H - 12H - 16H",
     "CARLTON TOWER - ASG - 2ª A 6ª - 07H - 11H - 12H - 16H"),
    ("INEP - 2ª A 6ª - 7:30H - 12H - 13H - 16:30H",
     "MME - 2ª A 6ª - 7:30H - 12H - 13H - 16:30H"),
    ("CFQ - 12X36 - 19H - 21H - 22H - 07H - ADICIONAL NOTURNO",
     "DKP - 12X36 - 19H - 21H - 22H - 07H - ADICIONAL NOTURNO"),
    # INEP e INEP ADM são clientes iguais mas jornadas diferentes (docstring
    # do módulo desde 2026-07-22) — segue valendo.
    ("INEP - 2ª A 6ª - 08H - 12H - 13H - 17H",
     "INEP ADM - 2ª A 6ª - 08H - 12H - 13H - 17H"),
):
    assert suspeitas([a, b]) == [], f"clientes diferentes viraram duplicata:\n {a}\n {b}"

# (3) MESMA jornada escrita de dois jeitos => É suspeita (os 3 casos reais)
reais = [
    ("GHS SEDE - 2ª A 5ª - 08H - 12H - 13H - 18H | 6ª 08H - 12H - 13H - 17H",
     "GHS SEDE - 2ª A 5ª - 08H - 12H - 13H - 18H | 6ª 08H - 12H - 13H - 17H|"),
    ("SEBRAE - 07H - 12H - 13H - 16H | SÁB. 07H - 12H - 13H - 16H",
     "SEBRAE - 07H - 12H - 13H - 16H | SÁB. 07H - 12H - 13H - 16H |"),
]
for a, b in reais:
    r = suspeitas([a, b])
    assert len(r) == 1, f"duplicata real não foi sinalizada:\n {a}\n {b}"
    assert r[0]["identicas_apos_normalizar"] is True, r[0]

# acento e typo conhecido continuam sendo pegos
r = suspeitas([
    "MTRANS - 12X36 - 19H - 07H - ADICIONAL NOTURNO",
    "MTRANS - 12X36 - 19H - 07H - ADICONAL NOTURNO",   # typo real dos dados
])
assert len(r) == 1, "typo ADICONAL deixou de ser reconhecido"

# ------------------------------------------------------- a fila encolheu
# Amostra representativa: 2 duplicatas reais no meio de jornadas legítimas que
# antes viravam ruído. O que sai tem que ser SÓ as duplicatas.
amostra = [
    "INTERMITENTE APOIO ADM - 2ª A 6ª - 07H - 12H - 13H -16H",
    "INTERMITENTE APOIO ADM - 2ª A 6ª - 07H - 12H - 13H -17H",
    "INTERMITENTE APOIO ADM - 2ª A 6ª - 08H - 12H - 13H -18H",
    "INEP - 2ª A 6ª - 7:30H - 12H - 13H - 16:30H",
    "MME - 2ª A 6ª - 7:30H - 12H - 13H - 16:30H",
    "CARLTON CENTER - ASG - 2ª A 6ª - 07H - 11H - 12H - 16H",
    "CARLTON TOWER - ASG - 2ª A 6ª - 07H - 11H - 12H - 16H",
    "SEBRAE - 07H - 12H - 13H - 16H | SÁB. 07H - 12H - 13H - 16H",
    "SEBRAE - 07H - 12H - 13H - 16H | SÁB. 07H - 12H - 13H - 16H |",
]
r = suspeitas(amostra)
assert len(r) == 1, f"esperava só a duplicata do SEBRAE, veio {len(r)}: {r}"
assert "SEBRAE" in r[0]["a"], r[0]

# lista vazia / item único não quebram
assert suspeitas([]) == []
assert suspeitas(["GHS SEDE - 2ª A 6ª - 08H - 17H"]) == []
assert suspeitas(["", "   ", None]) == []

print("test_jornada_duplicidade: OK")
