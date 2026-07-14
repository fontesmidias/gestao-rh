"""Teste de fumaça ponta a ponta: cadastro RH → link mágico → autosave → declaração →
upload de documentos (imagem→PDF no MinIO) → concluir envio."""

import io
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
from PIL import Image

from app.main import app

c = TestClient(app)

# 1) health
assert c.get("/api/health").json() == {"status": "ok"}

# 2) login RH (admin criado pelo bootstrap)
r = c.post("/api/rh/auth/login", json={"email": "rh@greenhousedf.com.br", "senha": "senha-teste-123"})
assert r.status_code == 200, r.text
rh = {"Authorization": f"Bearer {r.json()['token']}"}

# sem token -> 401
assert c.post("/api/rh/candidatos", json={}).status_code == 401

# 3) cadastro de candidato -> link mágico
r = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": "José Teste da Silva",
    "email": "jose@example.com",
    "celular_whatsapp": "+5561999998888",
})
assert r.status_code == 201, r.text
convite = r.json()
token = convite["link_magico"].rsplit("/c/", 1)[1]
assert convite["email_enviado"] is False  # SMTP não configurado: fallback ok

# 4) sessão do candidato + aceite LGPD
assert c.get(f"/api/c/{token}").status_code == 200
assert c.post(f"/api/c/{token}/aceite-lgpd").status_code == 204

# 5) autosave por seção (homem, 30 anos, casado, PCD não, com 1 dependente de 3 anos, VT sim)
assert c.put(f"/api/c/{token}/ficha/pessoais", json={
    "data_nascimento": "1996-03-10", "sexo": "masculino", "identidade_genero": "cisgenero",
    "cor_raca": "parda", "nacionalidade": "brasileira", "naturalidade_cidade": "Brasília",
    "naturalidade_uf": "DF", "estado_civil": "casado", "escolaridade": "medio_completo",
    "pcd": False,
}).status_code == 204
assert c.put(f"/api/c/{token}/ficha/endereco", json={
    "cep": "71250015", "logradouro_numero_complemento": "SCIA Q15 Cj 13 Lt 8",
    "bairro": "Zona Industrial", "cidade": "Brasília", "uf": "DF",
}).status_code == 204
assert c.put(f"/api/c/{token}/ficha/documentos", json={
    "rg_numero": "1234567", "rg_orgao_emissor": "SSP/DF", "rg_data_expedicao": "2015-05-10",
    "cpf": "39053344705", "pis_nis_pasep": "12345678901",
    "titulo_eleitor_numero": "123456789012", "titulo_eleitor_zona": "001",
    "titulo_eleitor_secao": "0042",
}).status_code == 204
assert c.put(f"/api/c/{token}/ficha/trabalho-banco", json={
    "tamanho_calca": "42", "tamanho_camisa": "M", "tamanho_calcado": "41",
    "banco": "BRB", "pix_tipo": "cpf", "pix_chave": "39053344705",
}).status_code == 204
assert c.put(f"/api/c/{token}/ficha/dependentes", json=[{
    "nome_completo": "Maria Teste", "data_nascimento": "2023-01-15",
    "cpf": "11144477735", "parentesco": "filho", "deduz_irrf": True,
}]).status_code == 204
assert c.put(f"/api/c/{token}/ficha/vt-emergencia", json={
    "vt_optante": True, "vt_cartao_dftrans": "123456",
    "usa_medicamento_continuo": False, "condicoes_medicas": "Nenhuma",
}).status_code == 204
assert c.put(f"/api/c/{token}/ficha/contatos-emergencia", json=[{
    "nome_completo": "Ana Teste", "parentesco": "esposa", "telefone_celular": "+5561988887777",
}]).status_code == 204

# 6) estado completo (continue de onde parou)
estado = c.get(f"/api/c/{token}/ficha").json()
assert estado["pessoais"]["nome_completo"] == "José Teste da Silva"
assert len(estado["dependentes"]) == 1

# 7) declaração de veracidade -> aguardando_assinatura
r = c.post(f"/api/c/{token}/ficha/declaracao")
assert r.status_code == 200, r.text
assert r.json()["status"] == "aguardando_assinatura"

# 7b) assinatura das 3 fichas: preview -> código por e-mail -> assinar (OTP)
import app.api.assinaturas as mod_ass

codigos = {}
_orig = mod_ass.enviar_email
mod_ass.enviar_email = lambda dest, assunto, corpo, html=None: codigos.__setitem__(
    "ultimo", corpo.split("assinatura é: ")[1][:6]) or True

for doc in ("ficha_cadastro", "ficha_emergencia", "termo_vt"):
    r = c.get(f"/api/c/{token}/fichas/{doc}/preview")
    assert r.status_code == 200 and r.content[:4] == b"%PDF", doc
    assert c.post(f"/api/c/{token}/fichas/{doc}/solicitar-codigo").status_code == 204
    r = c.post(f"/api/c/{token}/fichas/{doc}/assinar", json={"codigo": "000000"})
    assert r.status_code == 422, r.text  # código errado é recusado
    r = c.post(f"/api/c/{token}/fichas/{doc}/assinar", json={"codigo": codigos["ultimo"]})
    assert r.status_code == 200 and len(r.json()["hash_sha256"]) == 64, r.text
    assert c.post(f"/api/c/{token}/fichas/{doc}/solicitar-codigo").status_code == 409

mod_ass.enviar_email = _orig
fichas = c.get(f"/api/c/{token}/fichas").json()["fichas"]
assert all(f["assinado"] for f in fichas)

# 8) checklist: regras condicionais (homem 18-45 -> reservista; casado -> certidão;
#    dependente 3 anos -> nascimento + vacina; VT com cartão -> cartao_vt; sem PCD -> sem laudo)
check = c.get(f"/api/c/{token}/documentos").json()
tipos = {s["tipo"] for s in check["slots"]}
assert "reservista" in tipos and "cert_casamento" in tipos and "cartao_vt" in tipos
assert "cert_nascimento_dep" in tipos and "cartao_vacina_dep" in tipos
assert "laudo_pcd" not in tipos and "declaracao_escolar_dep" not in tipos

# 9) upload: imagem vira PDF no MinIO; arquivo ruim é recusado com código
slot_rg = next(s for s in check["slots"] if s["tipo"] == "rg")
img = Image.new("RGB", (900, 1200), "white")
buf = io.BytesIO(); img.save(buf, "JPEG")
r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("rg.jpg", buf.getvalue(), "image/jpeg")})
assert r.status_code == 200, r.text
assert r.json()["status"] == "enviado" and r.json()["paginas"] == 1

r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("x.txt", b"oi", "text/plain")})
assert r.status_code == 422 and r.json()["detail"] == "formato_nao_suportado"

# 10) concluir envio antes da hora -> 422 com a lista do que falta
r = c.post(f"/api/c/{token}/concluir-envio")
assert r.status_code == 422 and len(r.json()["detail"]["faltando"]) > 0

# 11) envia todos os obrigatórios restantes e conclui
check = c.get(f"/api/c/{token}/documentos").json()
for s in check["slots"]:
    if s["obrigatorio"] and s["status"] == "pendente":
        b = io.BytesIO(); Image.new("RGB", (900, 1200), "white").save(b, "JPEG")
        rr = c.post(f"/api/c/{token}/documentos/{s['id']}/arquivo",
                    files={"arquivo": (f"{s['tipo']}.jpg", b.getvalue(), "image/jpeg")})
        assert rr.status_code == 200, rr.text
r = c.post(f"/api/c/{token}/concluir-envio")
assert r.status_code == 200 and r.json()["status"] == "envio_concluido"

# 12) checklist congelado: novo upload é recusado
b = io.BytesIO(); Image.new("RGB", (900, 1200), "white").save(b, "JPEG")
r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("rg2.jpg", b.getvalue(), "image/jpeg")})
assert r.status_code == 409

print("SMOKE TEST COMPLETO: 12/12 etapas ok")
