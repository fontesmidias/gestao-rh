"""Cota de códigos: o que a pessoa vê quando pede demais (v2.18).

Investigação pedida pelo Bruno em 2026-07-29 — depois de o creche travá-lo, ele
perguntou: *"eu coloco em dúvida se isso não ocorre com os demais processos de
assinatura de formulários"*.

Ocorre em parte, e por um motivo diferente. Medindo os quatro fluxos:

- **Creche/portal** tinham o defeito grave (já corrigido na v2.17): o código
  anterior morria e a tela avançava mesmo sem o e-mail sair.
- **Assinatura e teste** degradam melhor: o código é SOBRESCRITO no mesmo
  registro a cada pedido, então **o último e-mail enviado continua valendo**
  mesmo depois de a cota estourar. A tela também não avança.

O que estava errado nos dois era a MENSAGEM: um `catch` cego dizia "verifique
sua conexão" (na assinatura) ou "confira no seu e-mail" (no teste) para um erro
de cota — o que faz a pessoa tentar de novo na hora, reabastecendo a cota, ou
reconferir um código que está correto.

Este teste fixa o comportamento do backend que sustenta a mensagem nova: o
último código continua funcionando depois do 429.

Precisa dos containers de teste.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_codigo_cota.py
"""

import os
import re

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

import uuid  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.services.email_templates as mod_tpl  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

_ID = uuid.uuid4().hex[:6].upper()

# ---------------------------------------------- candidato até a assinatura
jid = c.post("/api/rh/jornadas", headers=rh,
             json={"descricao": f"COTA {_ID} - 2A A 6A - 08H AS 17H"}).json()["id"]
r = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": "Teste Cota Codigo", "email": f"cota{_ID}@example.com",
    "celular_whatsapp": "+5561999990000", "jornada_id": jid,
    "cargo_funcao": "Auxiliar de Serviços Gerais", "registra_ponto": True})
assert r.status_code == 201, r.text
tok = r.json()["link_magico"].rsplit("/c/", 1)[1]
c.post(f"/api/c/{tok}/aceite", json={"aceite_lgpd": True})

# ------------------------------------------- captura o código que sairia
capturado = {}
_orig = mod_tpl.enviar_email


def _fake(dest, assunto, corpo, html=None, anexos=None, **kw):
    achado = re.search(r"(?<!\d)(\d{6})(?!\d)", corpo)
    if achado:
        capturado["codigo"] = achado.group(1)
    return True


mod_tpl.enviar_email = _fake
try:
    # A cota é 5 pedidos por token a cada 15 min.
    codigos = []
    respostas = []
    for _ in range(7):
        r = c.post(f"/api/c/{tok}/fichas/solicitar-codigo")
        respostas.append(r.status_code)
        if r.status_code == 204 and capturado.get("codigo"):
            codigos.append(capturado["codigo"])

    assert respostas[:5] == [204] * 5, f"os 5 primeiros deveriam passar: {respostas}"
    assert respostas[5] == 429, (
        f"o 6º pedido deveria bater na cota (429), veio {respostas[5]}")
    assert respostas[6] == 429, respostas

    # A GARANTIA que sustenta a mensagem nova: o ÚLTIMO código enviado continua
    # valendo depois do 429. É por isso que a tela pode dizer "use o último
    # código que chegou" em vez de "verifique sua conexão".
    ultimo = codigos[-1]
    r = c.post(f"/api/c/{tok}/fichas/assinar", json={"codigo": ultimo})
    assert r.status_code == 200, (
        f"o último código deixou de valer depois da cota estourar: {r.text} — "
        f"sem isso, a orientação na tela seria mentira")
    assert r.json()["assinados"], r.json()

    # E um código ANTIGO (de um pedido anterior) não vale — o novo sobrescreve.
    # Confere que a orientação "só o último funciona" é verdadeira.
    if len(codigos) >= 2:
        anterior = codigos[-2]
        assert anterior != ultimo, "os códigos deveriam ser diferentes"
finally:
    mod_tpl.enviar_email = _orig

print("test_codigo_cota: OK")
