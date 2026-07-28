"""Teste de NÃO-REGRESSÃO exigido pelo roundtable (party-mode, 2026-07-27)
antes de liberar o A2 (padronização em massa de cargos/jornadas do Tirvu):

    "o A2 mexe justamente no dado que alimenta o processo mais frágil do
    sistema — o Tirvu recusa calado linha malformada [...] gerar o export
    ANTES da importação em massa [...] rodar a importação [...] gerar o
    export DEPOIS [...] o resto do arquivo byte-idêntico. Qualquer outra
    célula alterada = a importação fez algo que ninguém pediu."

Usa o caso real do repositório (docs/importacao-tirvu-Paulo-Henrique-Benicio-
Pereira.xlsx é um export ANTES do de-para existir — cargo sai vazio, a
pendência que o A2 resolve). Aqui recriamos o mesmo cenário: um colaborador
com o cargo "ANALISTA DE DP JR." (existe em cargos.txt, id 105) e comparamos
`linha_tirvu` ANTES e DEPOIS de rodar a importação em massa via as rotas HTTP
reais (preview -> confirmar), célula a célula.

Precisa dos containers efêmeros (banco limpo — resíduo de outro teste que já
gravou cargo_tirvu pode mascarar uma regressão real).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_importacao_massa_nao_regride_export.py
"""

import os

os.environ.update(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@greenhousedf.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
)

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.db import SessionLocal
from app.models.candidato import Candidato

c = TestClient(app)

r = c.post("/api/rh/auth/login", json={"email": "rh@greenhousedf.com.br", "senha": "senha-teste-123"})
assert r.status_code == 200, r.text
rh = {"Authorization": f"Bearer {r.json()['token']}"}

_CAMINHO = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "jornadas e cargos")
_cargos_txt = os.path.join(_CAMINHO, "cargos.txt")

if not os.path.exists(_cargos_txt):
    print("test_importacao_massa_nao_regride_export: SKIP (docs/jornadas e cargos ausente)")
    raise SystemExit(0)

with open(_cargos_txt, encoding="utf-8") as f:
    texto_cargos = f.read()

# "ANALISTA DE DP JR." é o cargo id=105 em cargos.txt (CBO 252105) — usado
# como exemplo no próprio CLAUDE.md ("cargo analista df jr=50" é outro
# exemplo do doc; aqui usamos o que realmente está no arquivo real).
CARGO_ALVO = "ANALISTA DE DP JR."
assert CARGO_ALVO in texto_cargos, "cargo de teste não está em cargos.txt — ajuste o teste"

jr = c.post("/api/rh/jornadas", headers=rh,
           json={"descricao": "TESTE NAO-REGRESSAO - 2A A 6A - 08H AS 17H"})
assert jr.status_code == 201, jr.text
jornada_id = jr.json()["id"]

conv = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": "Colaborador Teste Nao Regressao",
    "jornada_id": jornada_id,
    "cargo_funcao": CARGO_ALVO,
})
assert conv.status_code == 201, conv.text
candidato_id = conv.json()["candidato"]["id"]


def linha_do_candidato():
    """Gera a linha do Tirvu para o candidato de teste diretamente via
    linha_tirvu (mesma função usada por test_export_tirvu.py e pelo export
    real) — não depende de o candidato estar efetivado, porque o A2 mexe no
    de-para de cargo/jornada, não no funil de admissão."""
    from app.services.export_tirvu import linha_tirvu
    with SessionLocal() as db:
        cand = db.get(Candidato, candidato_id)
        return linha_tirvu(db, cand, gerar_matricula=False)


linha_antes = linha_do_candidato()
assert linha_antes["Cargo"] == "", (
    "pré-condição do teste falhou: o cargo já tinha ID antes da importação "
    "(resíduo de outro teste? recrie os containers efêmeros)")

# ---------- Roda a importação em massa (preview -> confirmar), como o RH faria ----------

prev = c.post("/api/rh/tirvu-txt/preview-cargos", headers=rh, json={"texto": texto_cargos})
assert prev.status_code == 200, prev.text
propostas = prev.json()["propostas"]
proposta_alvo = next(p for p in propostas if p["cargo"].strip().upper() == CARGO_ALVO)
assert proposta_alvo["aplicar_sugerido"], "cargo de teste não deveria ser ambíguo"

itens = [{"tirvu_id": p["tirvu_id"], "cargo": p["cargo"], "aplicar": p["aplicar_sugerido"]}
         for p in propostas]
conf = c.post("/api/rh/tirvu-txt/confirmar-cargos", headers=rh, json={"itens": itens})
assert conf.status_code == 200, conf.text
assert conf.json()["gravados"] > 0

# ---------- Compara linha ANTES x DEPOIS: SÓ o Cargo pode ter mudado ----------

linha_depois = linha_do_candidato()

assert linha_depois["Cargo"] == proposta_alvo["tirvu_id"], (
    f"esperado Cargo={proposta_alvo['tirvu_id']!r}, veio {linha_depois['Cargo']!r}")
assert linha_depois["Cargo"] != linha_antes["Cargo"]

diffs = {k: (linha_antes.get(k), linha_depois.get(k))
        for k in set(linha_antes) | set(linha_depois)
        if linha_antes.get(k) != linha_depois.get(k)}
assert diffs == {"Cargo": (linha_antes["Cargo"], linha_depois["Cargo"])}, (
    f"a importação em massa alterou colunas além do Cargo — REGRESSÃO: {diffs}")

print("test_importacao_massa_nao_regride_export: OK")
