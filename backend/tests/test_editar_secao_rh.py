"""Teste da rota PUT /rh/candidatos/{id}/ficha/{secao} (rh_ficha.py::editar_secao).

Cobre o bug de campo 2026-07-27: "quando o RH tenta corrigir manualmente os
dados da ficha, não salva e não diz o motivo". A causa raiz era uma
pydantic.ValidationError levantada FORA do ciclo de validação do FastAPI (o
corpo é um dict livre) — isso escapava como HTTP 500 em texto puro, sem detail
algum. Cada caso abaixo tem que devolver 422 nomeando o campo, NUNCA 500.

Precisa dos containers efêmeros (ver CLAUDE.md — banco+MinIO limpos).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_editar_secao_rh.py
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

from app.main import app

c = TestClient(app)

r = c.post("/api/rh/auth/login", json={"email": "rh@greenhousedf.com.br", "senha": "senha-teste-123"})
assert r.status_code == 200, r.text
rh = {"Authorization": f"Bearer {r.json()['token']}"}

jr = c.post("/api/rh/jornadas", headers=rh, json={"descricao": "EDITAR-SECAO - 2A A 6A - 08H AS 17H"})
assert jr.status_code == 201, jr.text
jornada_id = jr.json()["id"]

r = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": "Maria Teste Editar Secao",
    "jornada_id": jornada_id,
    "cargo_funcao": "Auxiliar de Serviços Gerais",
    # registra_ponto passou a ser obrigatório no convite (v2.44)
    "registra_ponto": True,
})
assert r.status_code == 201, r.text
candidato_id = r.json()["candidato"]["id"]


def editar(secao, dados, motivo="teste automatizado"):
    return c.put(f"/api/rh/candidatos/{candidato_id}/ficha/{secao}", headers=rh,
                json={"dados": dados, "motivo": motivo})


# ---------- Casos que ANTES da correção viravam 500 mudo ----------

# Data mal formatada (dd/mm/aaaa em vez de ISO) — SecaoPessoais.data_nascimento
r = editar("pessoais", {"data_nascimento": "15/03/1990"})
assert r.status_code == 422, r.text
assert r.status_code != 500
detail = r.json()["detail"]
assert isinstance(detail, list) and any("data_nascimento" in str(e.get("loc", [])) for e in detail), r.text

# Enum inválido — SecaoTrabalhoBanco.pix_tipo aceita só cpf/celular/email/aleatoria
r = editar("trabalho-banco", {"pix_tipo": "PIX"})
assert r.status_code == 422, r.text
assert r.status_code != 500

# CPF com dígito verificador errado — validador de ficha.py
r = editar("documentos", {"cpf": "11111111111"})
assert r.status_code == 422, r.text
assert r.status_code != 500

# UF por extenso: a normalização do backend agora corta para 2 letras
# maiúsculas ANTES da validação (Distrito Federal -> "DI"), então isto passa
# — não é o teste de UF inválida, é o de que não quebra em 500 nem quando o
# formato de entrada é inesperado.
r = editar("pessoais", {"naturalidade_uf": "distrito federal"})
assert r.status_code in (200, 422), r.text
assert r.status_code != 500

# CEP com hífen — normalizado para dígitos antes da validação
r = editar("endereco", {"cep": "70000-000", "bairro": "Asa Sul", "cidade": "Brasília", "uf": "df"})
assert r.status_code == 200, r.text
assert r.json()["campos_alterados"]

# tipo_sanguineo por extenso: coluna String(4) — não quebra em 500, e se
# estourar no commit vira 422 nomeando o campo (DataError capturado)
r = editar("vt-emergencia", {"tipo_sanguineo": "A POSITIVO EXTENSO DEMAIS"})
assert r.status_code in (200, 422), r.text
assert r.status_code != 500
if r.status_code == 422:
    assert "tipo_sanguineo" in str(r.json()["detail"])

# ---------- Casos que devem continuar funcionando normalmente ----------

# Edição válida simples
r = editar("pessoais", {"nome_social": "Maria T."})
assert r.status_code == 200, r.text
assert r.json()["campos_alterados"] == ["nome_social"]

# Sem motivo -> 422 (comportamento preexistente, não deve regredir)
r = c.put(f"/api/rh/candidatos/{candidato_id}/ficha/pessoais", headers=rh,
          json={"dados": {"nome_social": "X"}, "motivo": "  "})
assert r.status_code == 422 and r.json()["detail"] == "motivo_obrigatorio", r.text

# Seção desconhecida -> 404 (comportamento preexistente)
r = editar("secao-inexistente", {"x": "y"})
assert r.status_code == 404 and r.json()["detail"] == "secao_desconhecida", r.text

# ---------- Handler global: erro genérico não vaza o motivo real ----------
# Não dá para forçar um erro 100% genérico sem mockar internals; a garantia
# de que o handler nunca ecoa str(exc) é coberta à parte (ver main.py).

print("test_editar_secao_rh: OK")
