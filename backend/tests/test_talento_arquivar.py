"""Arquivar talento com motivo registrado no mini-CRM (v2.14).

Feedback 2026-07-28: "seria interessante que abrisse algo para colocar alguma
observação e também arquivo, para que o RH escrevesse algo por ocasião do
arquivamento, bem como foi o responsável por aquela ação e quando foi feito. E
também ser possível desfazer aquela ação."

Tudo isso já existia no mini-CRM (`Anotacao`: texto, anexo, autor SNAPSHOT e
data), então o arquivamento passou a ESCREVER lá em vez de ganhar campos
próprios — o histórico da pessoa fica num lugar só e anexar documento já
funciona pela tela de anotações. Desfazer é mudar o status de volta; o registro
permanece, porque a anotação é append-only.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_talento_arquivar.py
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

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@exemplo.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}


def _novo_talento(nome: str) -> str:
    # ⚠️ E-mail ÚNICO por execução. Era derivado do nome (`fulano@example.com`),
    # fixo entre rodadas — e desde a v3.05.0 o cadastro público DEDUPLICA por
    # e-mail: a segunda execução reusaria o talento da primeira. Pior aqui do
    # que em outros testes, porque este ARQUIVA talentos, e o recadastro reabre
    # quem está arquivado como "novo": o teste verificaria um estado que ele
    # mesmo acabou de desfazer, e a falha não falaria da causa.
    import uuid as _uuid
    sufixo = _uuid.uuid4().hex[:8]
    r = c.post("/api/talentos", json={
        "nome": nome, "email": f"{nome.split()[0].lower()}-{sufixo}@example.com",
        "cargos_interesse": ["Recepcionista"], "consentimento_lgpd": True})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _anotacoes(tid: str) -> list[dict]:
    r = c.get(f"/api/rh/crm/pessoa?talento_id={tid}", headers=rh)
    assert r.status_code == 200, r.text
    return r.json()["anotacoes"]


# --------------------------------------------- arquivar grava a anotação
tid = _novo_talento("Joana Arquivo Teste")
assert _anotacoes(tid) == [], "talento novo não deveria ter anotação"

r = c.put(f"/api/rh/talentos/{tid}/status", headers=rh,
          json={"status": "arquivado", "motivo": "Não atende ao perfil do posto"})
assert r.status_code == 200 and r.json()["status"] == "arquivado", r.text

notas = _anotacoes(tid)
assert len(notas) == 1, f"o motivo deveria ter virado anotação: {notas}"
n = notas[0]
assert "Arquivado" in n["texto"] and "Não atende ao perfil" in n["texto"], n
# autor e data — foi o que o RH pediu ("quem foi o responsável e quando")
assert n["autor"], f"anotação sem autor: {n}"
assert n["quando"], f"anotação sem data: {n}"

# ------------------------------------------------- desfazer (reabrir) e o
# registro do que houve PERMANECE (a anotação é append-only)
r = c.put(f"/api/rh/talentos/{tid}/status", headers=rh,
          json={"status": "novo", "motivo": "Abriu vaga nova no mesmo posto"})
assert r.status_code == 200 and r.json()["status"] == "novo", r.text

notas = _anotacoes(tid)
assert len(notas) == 2, f"a reabertura deveria somar outra anotação: {notas}"
textos = " | ".join(x["texto"] for x in notas)
assert "Arquivado" in textos and "Reaberto" in textos, textos

# ------------------------------------------------------- motivo é opcional
tid2 = _novo_talento("Marcos Sem Motivo")
r = c.put(f"/api/rh/talentos/{tid2}/status", headers=rh, json={"status": "arquivado"})
assert r.status_code == 200, r.text
assert _anotacoes(tid2) == [], "sem motivo, não inventa anotação"

# motivo só com espaços também não cria anotação vazia
tid3 = _novo_talento("Paula Espacos")
c.put(f"/api/rh/talentos/{tid3}/status", headers=rh,
      json={"status": "arquivado", "motivo": "    "})
assert _anotacoes(tid3) == [], "motivo em branco não pode virar anotação"

# --------------------------------------------------- convertido não muda
tid4 = _novo_talento("Rita Convertida")
r = c.post(f"/api/rh/talentos/{tid4}/converter", headers=rh)
assert r.status_code in (200, 201), r.text
r = c.put(f"/api/rh/talentos/{tid4}/status", headers=rh,
          json={"status": "arquivado", "motivo": "x"})
assert r.status_code == 409 and r.json()["detail"] == "talento_ja_convertido", r.text
assert _anotacoes(tid4) == [], "recusou o status mas gravou anotação assim mesmo"

# ------------------------------------------- resumo das anotações na LINHA
# (v2.15) O RH via "🗒️ Anotações" em todo mundo e só descobria que não havia
# nada depois de abrir o modal. A listagem agora diz quantas e qual a última.
def _da_lista(tid: str) -> dict:
    return next(x for x in c.get("/api/rh/talentos", headers=rh).json() if x["id"] == tid)


tid5 = _novo_talento("Bruna Resumo Linha")
linha = _da_lista(tid5)
assert linha["anotacoes"] == 0 and linha["ultima_anotacao"] is None, linha

for txt in ("Primeira conversa por telefone", "Aceita o turno da noite"):
    assert c.post("/api/rh/crm/anotacoes", headers=rh,
                  json={"talento_id": tid5, "texto": txt}).status_code in (200, 201)

linha = _da_lista(tid5)
assert linha["anotacoes"] == 2, linha
assert "turno da noite" in linha["ultima_anotacao"], (
    f"a última tem que ser a MAIS RECENTE: {linha['ultima_anotacao']!r}")
assert linha["ultima_anotacao_autor"], "resumo sem autor"
assert linha["ultima_anotacao_quando"], "resumo sem data"

# o arquivamento também aparece no resumo (é anotação como qualquer outra)
c.put(f"/api/rh/talentos/{tid5}/status", headers=rh,
      json={"status": "arquivado", "motivo": "Posto encerrado"})
linha = _da_lista(tid5)
assert linha["anotacoes"] == 3 and "Posto encerrado" in linha["ultima_anotacao"], linha

# sem N+1: o resumo é carregado em LOTE, como as tags.
# O teste compara duas listagens de tamanhos diferentes: se o número de
# queries acompanhar o de talentos, é N+1. Um limite absoluto não serviria —
# mediria o tamanho do banco, que cresce a cada execução, e não o padrão de
# acesso.
from sqlalchemy import event  # noqa: E402

from app.core.db import engine  # noqa: E402


def _queries_do_listar(**filtros) -> tuple[int, int]:
    n = {"q": 0}
    ouvinte = lambda *a, **k: n.__setitem__("q", n["q"] + 1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", ouvinte)
    try:
        linhas = c.get("/api/rh/talentos", headers=rh, params=filtros).json()
    finally:
        event.remove(engine, "before_cursor_execute", ouvinte)
    return len(linhas), n["q"]


_n_todos, _q_todos = _queries_do_listar()
_n_um, _q_um = _queries_do_listar(busca="Bruna Resumo Linha")
assert _n_todos > _n_um, f"a busca deveria filtrar ({_n_todos} x {_n_um})"
# a diferença de queries não pode acompanhar a diferença de talentos
assert _q_todos - _q_um <= 3, (
    f"{_q_todos} queries para {_n_todos} talentos x {_q_um} para {_n_um} — "
    f"o custo cresce com o volume: o resumo de anotações voltou a ser N+1")

print("test_talento_arquivar: OK")
