"""Reabertura do próprio envio pelo candidato (v2.03, feedback 2026-07-28).

A pessoa clicava em "CONCLUÍ MEU ENVIO", percebia na hora que tinha mandado o
documento errado — e não tinha como voltar: `documentos.py` congela o
checklist em `envio_concluido` (409) e só o RH reabria. Quem tem menos recurso
é justamente quem mais erra no envio e menos consegue pedir socorro.

Agora existe `POST /c/{token}/reabrir-envio`, com uma guarda: se o RH JÁ
revisou qualquer slot (aprovado/rejeitado/dispensado), a porta não reabre —
trocar um arquivo já analisado faria a análise do RH valer para um documento
que não existe mais. Nesse caso o caminho continua sendo o RH reabrir o slot.

Precisa dos containers de teste. Este teste roda DEPOIS do smoke_test na
mesma base (reusa o candidato que o smoke deixou pronto) OU cria o seu.
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_reabrir_envio.py
"""

import io
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
from PIL import Image, ImageDraw  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)


def _nitida() -> bytes:
    """Imagem lisa é recusada com 422 imagem_borrada — precisa de bordas."""
    im = Image.new("RGB", (900, 1200), "white")
    dr = ImageDraw.Draw(im)
    for i in range(28):
        dr.text((40, 30 + i * 40), f"DOCUMENTO 1234567 SSP-DF LINHA {i}", fill="black")
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@exemplo.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}
jid = c.post("/api/rh/jornadas", headers=rh,
             json={"descricao": "REABRIR - TESTE"}).json()["id"]


def _candidato_pronto_para_concluir() -> str:
    """Cria um candidato e envia TODOS os obrigatórios; devolve o token."""
    r = c.post("/api/rh/candidatos", headers=rh, json={
        "nome_completo": "Ana Reabertura Teste", "email": "ana.reabrir@example.com",
        "celular_whatsapp": "+5561999996666", "jornada_id": jid,
        "cargo_funcao": "Auxiliar de Serviços Gerais", "registra_ponto": True})
    tok = r.json()["link_magico"].rsplit("/c/", 1)[1]
    c.post(f"/api/c/{tok}/aceite", json={"aceite_lgpd": True})
    for s in c.get(f"/api/c/{tok}/documentos").json()["slots"]:
        if s["obrigatorio"] and s["status"] == "pendente":
            c.post(f"/api/c/{tok}/documentos/{s['id']}/arquivo",
                   files={"arquivo": ("d.jpg", _nitida(), "image/jpeg")})
    return tok


# ------------------------------------------------- caminho feliz: reabre
tok = _candidato_pronto_para_concluir()
r = c.post(f"/api/c/{tok}/concluir-envio")
assert r.status_code == 200, r.text
assert r.json()["status"] == "envio_concluido", r.text

# com o envio concluído, o checklist está congelado
slots = c.get(f"/api/c/{tok}/documentos").json()["slots"]
algum = next(s for s in slots if s["status"] == "enviado")
r = c.post(f"/api/c/{tok}/documentos/{algum['id']}/arquivo",
           files={"arquivo": ("x.jpg", _nitida(), "image/jpeg")})
assert r.status_code == 409 and r.json()["detail"] == "envio_ja_concluido", r.text

# a pessoa reabre SOZINHA
r = c.post(f"/api/c/{tok}/reabrir-envio")
assert r.status_code == 200, r.text
assert r.json()["status"] == "docs_pendentes", r.text

# e agora consegue trocar o documento
r = c.post(f"/api/c/{tok}/documentos/{algum['id']}/arquivo",
           files={"arquivo": ("novo.jpg", _nitida(), "image/jpeg")})
assert r.status_code == 200, f"reabriu mas não deixou trocar: {r.text}"

# reabrir de novo sem ter concluído é 409 (não é botão de repetição)
r = c.post(f"/api/c/{tok}/reabrir-envio")
assert r.status_code == 409 and r.json()["detail"] == "envio_nao_concluido", r.text

# ------------------------------------------- guarda: RH já olhou => 409
tok2 = _candidato_pronto_para_concluir()
assert c.post(f"/api/c/{tok2}/concluir-envio").status_code == 200
slots2 = c.get(f"/api/c/{tok2}/documentos").json()["slots"]
alvo = next(s for s in slots2 if s["status"] == "enviado")
assert c.post(f"/api/rh/slots/{alvo['id']}/aprovar", headers=rh).status_code == 200

r = c.post(f"/api/c/{tok2}/reabrir-envio")
assert r.status_code == 409 and r.json()["detail"] == "rh_ja_revisou", (
    "com documento já revisado pelo RH, a reabertura tem que ser recusada — "
    "senão a análise do RH valeria para um arquivo que não existe mais: "
    f"{r.status_code} {r.text}")

print("test_reabrir_envio: OK")
