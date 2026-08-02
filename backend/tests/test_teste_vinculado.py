"""Aproveitar teste já respondido para um candidato (v2.21).

Pedido do Bruno (2026-07-29): "quero que, ao criar o link para enviar a
documentação, vincular algum teste que a pessoa já fez — DISC, situacional ou
alguma prova que eu criei; isso não precisa aparecer para o candidato, mas sim
para o RH".

O que este teste protege:

1. **A identidade é registrada como o que é.** Quando o teste veio pelo Banco
   de Talentos, o sistema sabe de quem é (`automatico=True`). Quando o RH
   escolheu da lista pelo nome, é julgamento humano (`automatico=False`, com
   autor). O link avulso é anônimo — `ParticipanteTestagem` guarda só o nome —
   e teste decide contratação: quem consultar depois precisa saber a diferença.
2. **Aponta, não copia.** O resultado é lido na origem; se o vínculo copiasse,
   haveria duas versões do mesmo dado.
3. **O candidato não vê.** Não entra no wizard nem no dossiê, que circula.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_teste_vinculado.py
"""

import os
import uuid as _uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@greenhousedf.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

_ID = _uuid.uuid4().hex[:6].upper()


def _teste_avulso_respondido(nome: str) -> str:
    """Cria um link de testagem, responde o DISC até CONCLUIR e devolve o
    participante_id. Usa as rotas reais de `api/testagem.py`."""
    r = c.post("/api/rh/testagem/links", headers=rh,
               json={"nome": f"Triagem {_ID}", "tem_disc": True,
                     "tem_situacional": False})
    assert r.status_code == 201, r.text
    token = r.json()["url"].rsplit("/t/", 1)[1]

    r = c.post(f"/api/t/{token}/participar", json={"nome": nome})
    assert r.status_code == 201, r.text
    pid = r.json()["participante_id"]

    assert c.post(f"/api/t/{token}/p/{pid}/disc/iniciar").status_code == 200
    questoes = c.get(f"/api/t/{token}/p/{pid}/disc/questoes").json()
    for q in questoes.get("questoes", questoes if isinstance(questoes, list) else []):
        opcoes = q["opcoes"]
        c.post(f"/api/t/{token}/p/{pid}/disc/responder", json={
            "grupo": q.get("grupo", q.get("id")),
            "mais": opcoes[0]["palavra"], "menos": opcoes[-1]["palavra"]})
    r = c.post(f"/api/t/{token}/p/{pid}/disc/concluir")
    assert r.status_code == 200 and r.json()["status"] == "concluido", r.text
    return pid


# ------------------------------------------------------------- exige login
assert c.get("/api/rh/testes-vinculaveis").status_code == 401

# --------------------------------------------------- candidato para receber
jid = c.post("/api/rh/jornadas", headers=rh,
             json={"descricao": f"VINC {_ID} - 2A A 6A - 08H AS 17H"}).json()["id"]
r = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": f"Candidato Vinculo {_ID}", "email": f"vinc{_ID}@example.com",
    "jornada_id": jid, "cargo_funcao": "Auxiliar de Serviços Gerais", "registra_ponto": True})
assert r.status_code == 201, r.text
cid = r.json()["candidato"]["id"]

# ainda não tem nada aproveitado
assert c.get(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh).json() == []

# --------------------------------------- um teste avulso, respondido por alguém
pid = _teste_avulso_respondido(f"Jose Silva {_ID}")

lista = c.get("/api/rh/testes-vinculaveis", headers=rh).json()
meu = next((x for x in lista if x["referencia_id"] == pid), None)
assert meu is not None, "o teste respondido não apareceu como vinculável"
# CONTEXTO para o RH reconhecer a pessoa — é o ponto do desenho
for campo in ("nome_respondente", "quando", "o_que", "link_nome", "identificado"):
    assert campo in meu, f"falta '{campo}' no item: {meu}"
assert meu["identificado"] is False, (
    "link avulso é anônimo — não pode se dizer identificado")
assert f"Jose Silva {_ID}" == meu["nome_respondente"], meu

# busca por nome filtra
assert any(x["referencia_id"] == pid for x in c.get(
    f"/api/rh/testes-vinculaveis?busca=Jose Silva {_ID}", headers=rh).json())
assert not [x for x in c.get(
    "/api/rh/testes-vinculaveis?busca=zzz-nao-existe", headers=rh).json()]

# ------------------------------------------------------------- vincular
r = c.post(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh,
           json={"origem": "testagem", "referencia_id": pid})
assert r.status_code == 201, r.text
v = r.json()
assert v["origem"] == "testagem", v
# escolha do RH => NÃO é automático, e fica registrado quem afirmou
assert v["automatico"] is False, v
assert v["vinculado_por"] == "rh@greenhousedf.com.br", v
assert v.get("testes"), "o resultado deveria vir junto (lido na origem)"

# sai da lista de disponíveis (não se aproveita o mesmo teste duas vezes)
assert not [x for x in c.get("/api/rh/testes-vinculaveis", headers=rh).json()
            if x["referencia_id"] == pid]

# aparece na ficha
vinculados = c.get(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh).json()
assert len(vinculados) == 1 and vinculados[0]["id"] == v["id"], vinculados

# vincular de novo é idempotente (não duplica)
r = c.post(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh,
           json={"origem": "testagem", "referencia_id": pid})
assert r.status_code == 201, r.text
assert len(c.get(f"/api/rh/candidatos/{cid}/testes-vinculados",
                 headers=rh).json()) == 1

# ------------------------------------------------- aparece na lista de Admissões
linha = next(x for x in c.get("/api/rh/candidatos", headers=rh).json()
             if x["id"] == cid)
assert linha["testes_vinculados"] == 1, linha

# ------------------------------------------- o CANDIDATO não vê (nem o dossiê)
# a rota é do painel e exige login; não há equivalente em /c/{token}
assert c.get(f"/api/rh/candidatos/{cid}/testes-vinculados").status_code == 401

# --------------------------------------------------------------- desvincular
r = c.delete(f"/api/rh/candidatos/{cid}/testes-vinculados/{v['id']}", headers=rh)
assert r.status_code == 204, r.text
assert c.get(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh).json() == []
# e volta a ficar disponível — o RH pode ter reconhecido a pessoa errada
assert any(x["referencia_id"] == pid
           for x in c.get("/api/rh/testes-vinculaveis", headers=rh).json())

# --------------------------------------------------------- erros tratados
assert c.post(f"/api/rh/candidatos/{cid}/testes-vinculados", headers=rh,
              json={"origem": "inventada", "referencia_id": pid}).status_code == 422
assert c.post(f"/api/rh/candidatos/{_uuid.uuid4()}/testes-vinculados", headers=rh,
              json={"origem": "testagem", "referencia_id": pid}).status_code == 404
assert c.delete(f"/api/rh/candidatos/{cid}/testes-vinculados/{_uuid.uuid4()}",
                headers=rh).status_code == 404

print("test_teste_vinculado: OK")
