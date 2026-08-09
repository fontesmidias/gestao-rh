"""Confirmação em lote da estrutura das jornadas (v2.13, feedback 2026-07-28).

O RH pediu ação em massa nas 325 jornadas "A confirmar". Diferente da fila de
duplicidades — que a medição mostrou ser 99% ruído e virou correção do detector
(v2.12) —, aqui o volume é REAL: das 269 jornadas da planilha de escalas, 86%
saem com confiança ALTA e o resto é 12X36 que o parser lê certo. Confirmar uma
a uma são 325 cliques para nada.

O lote é seguro aqui porque grava METADADO INTERNO: a `descricao` canônica (a
que vai ao Tirvu) não é tocada e o RH reedita qualquer campo depois. Ainda
assim, o padrão confirma só as de ALTA confiança — as de média ficam para o
olho humano, que é onde o parser erra.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_jornadas_confirmar_lote.py
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@exemplo.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

import uuid  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@exemplo.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

# ------------------------------------------------------------ exige login
assert c.get("/api/rh/jornadas-a-confirmar").status_code == 401
assert c.post("/api/rh/jornadas/confirmar-lote", json={}).status_code == 401

# ------------------------------------------- descrições REAIS da planilha
# Duas de alta confiança (escala + 4 horários) e uma 12X36, que o parser lê
# só em parte — é justamente a que NÃO pode ser confirmada no escuro.
# Sufixo único por execução: a descrição é `unique=True`, então repetir o
# teste no MESMO banco recriaria as jornadas e o segundo run falharia — teste
# que só passa em banco limpo falha no CI de alguém sem explicar por quê.
_ID = uuid.uuid4().hex[:6].upper()
ALTA = [
    f"LOTE {_ID} A - 2ª A 6ª - 08H - 12H - 13H - 17H",
    f"LOTE {_ID} B - 2ª A 6ª - 07H - 11H - 12H - 16H",
]
PARCIAL = f"LOTE {_ID} C - 12X36 - 19H - 07H - ADICIONAL NOTURNO"

ids = {}
for d in ALTA + [PARCIAL]:
    r = c.post("/api/rh/jornadas", headers=rh, json={"descricao": d})
    assert r.status_code == 201, r.text
    ids[d] = r.json()["id"]

fila = c.get("/api/rh/jornadas-a-confirmar", headers=rh).json()
minhas = {j["id"]: j for j in fila["jornadas"] if j["id"] in ids.values()}
assert len(minhas) == 3, f"as 3 criadas deveriam estar na fila: {len(minhas)}"
assert minhas[ids[ALTA[0]]]["confianca"] == "alta", minhas[ids[ALTA[0]]]
assert minhas[ids[PARCIAL]]["confianca"] != "alta", (
    "12X36 sem os 4 horários não pode sair como alta confiança — é o caso que "
    "precisa do olho humano")

# ------------------------------------------- lote confirma SÓ a alta confiança
antes_alta = fila["por_confianca"]["alta"]
r = c.post("/api/rh/jornadas/confirmar-lote", headers=rh, json={"confianca": "alta"})
assert r.status_code == 200, r.text
# >= porque a fila pode ter jornadas de outras execuções; o que importa é que
# NENHUMA de alta confiança ficou para trás (conferido logo abaixo).
assert r.json()["confirmadas"] == antes_alta, r.json()

depois = c.get("/api/rh/jornadas-a-confirmar", headers=rh).json()
assert depois["por_confianca"]["alta"] == 0, "sobrou alta confiança por confirmar"
restantes = {j["id"] for j in depois["jornadas"]}
assert ids[PARCIAL] in restantes, (
    "a 12X36 foi confirmada no escuro — o lote só pode pegar alta confiança")
for d in ALTA:
    assert ids[d] not in restantes, f"'{d}' deveria ter saído da fila"

# --------------------------------------- confirmou E gravou os campos mesmo
jornadas = {j["id"]: j for j in c.get("/api/rh/jornadas", headers=rh).json()}
alvo = jornadas[ids[ALTA[0]]]
assert alvo["estruturado"] is True, alvo
assert alvo["hora_entrada"] == "08:00", f"campo não gravado: {alvo}"
assert alvo["hora_saida"] == "17:00", alvo
# a DESCRIÇÃO canônica (a que vai ao Tirvu) não pode ter mudado
assert alvo["descricao"] == ALTA[0], (
    f"o lote alterou a descrição canônica: {alvo['descricao']!r}")

# ---------------------------------- ids explícitos passam por cima da confiança
# (o RH revisou aquela 12X36 na tela e mandou confirmar; é decisão dele)
r = c.post("/api/rh/jornadas/confirmar-lote", headers=rh,
           json={"jornada_ids": [ids[PARCIAL]]})
assert r.status_code == 200 and r.json()["confirmadas"] == 1, r.text
assert ids[PARCIAL] not in {
    j["id"] for j in c.get("/api/rh/jornadas-a-confirmar", headers=rh).json()["jornadas"]}

# rodar de novo não confirma nada (nada pendente daquelas) e não quebra
r = c.post("/api/rh/jornadas/confirmar-lote", headers=rh,
           json={"jornada_ids": [ids[PARCIAL]]})
assert r.status_code == 200 and r.json()["confirmadas"] == 0, r.text

print("test_jornadas_confirmar_lote: OK")
