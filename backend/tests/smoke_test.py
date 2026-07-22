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
assert c.get("/api/health").json().get("status") == "ok"

# 2) login RH (admin criado pelo bootstrap)
r = c.post("/api/rh/auth/login", json={"email": "rh@greenhousedf.com.br", "senha": "senha-teste-123"})
assert r.status_code == 200, r.text
rh = {"Authorization": f"Bearer {r.json()['token']}"}

# sem token -> 401
assert c.post("/api/rh/candidatos", json={}).status_code == 401

# 3) cadastro de candidato -> link mágico
# jornada é obrigatória no convite (feedback 2026-07-21) — sem ela, 422
jr = c.post("/api/rh/jornadas", headers=rh, json={"descricao": "SMOKE - 2A A 6A - 08H AS 17H"})
assert jr.status_code == 201, jr.text
jornada_id = jr.json()["id"]
sem_jornada = c.post("/api/rh/candidatos", headers=rh, json={"nome_completo": "Sem Jornada"})
assert sem_jornada.status_code == 422 and sem_jornada.json()["detail"] == "jornada_obrigatoria", sem_jornada.text
r = c.post("/api/rh/candidatos", headers=rh, json={
    "nome_completo": "José Teste da Silva",
    "email": "jose@example.com",
    "celular_whatsapp": "+5561999998888",
    "jornada_id": jornada_id,
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

# 7b) assinatura: 1 código único -> preview -> assina os 3 -> vias assinadas anexadas
import app.api.assinaturas as mod_ass

capturado = {}
_orig = mod_ass.enviar_email
def _fake_email(dest, assunto, corpo, html=None, anexos=None, **kw):
    if "código de assinatura" in corpo:
        capturado["codigo"] = corpo.split("eletrônica é: ")[1][:6]
    if anexos:
        capturado["anexos"] = anexos
    return True
mod_ass.enviar_email = _fake_email

FICHAS = ("ficha_cadastro", "ficha_emergencia", "termo_vt", "acordo_confidencialidade")
for doc in FICHAS:
    r = c.get(f"/api/c/{token}/fichas/{doc}/preview")
    assert r.status_code == 200 and r.content[:4] == b"%PDF", doc

assert c.post(f"/api/c/{token}/fichas/solicitar-codigo").status_code == 204
r = c.post(f"/api/c/{token}/fichas/assinar", json={"codigo": "000000"})
assert r.status_code == 422, r.text  # código errado é recusado
r = c.post(f"/api/c/{token}/fichas/assinar", json={"codigo": capturado["codigo"]})
assert r.status_code == 200 and len(r.json()["assinados"]) == len(FICHAS), r.text
assert len(capturado["anexos"]) == len(FICHAS)  # vias assinadas enviadas ao candidato
assert all(a[1][:4] == b"%PDF" for a in capturado["anexos"])
assert c.post(f"/api/c/{token}/fichas/solicitar-codigo").status_code == 409  # tudo assinado

mod_ass.enviar_email = _orig
fichas = c.get(f"/api/c/{token}/fichas").json()["fichas"]
assert all(f["assinado"] for f in fichas)
# preview agora devolve a via assinada (bloco de assinatura embutido)
r = c.get(f"/api/c/{token}/fichas/ficha_cadastro/preview")
assert r.status_code == 200 and r.content[:4] == b"%PDF"

# 8) checklist: regras condicionais (homem 18-45 -> reservista; casado -> certidão;
#    dependente 3 anos -> nascimento + vacina; VT com cartão -> cartao_vt; sem PCD -> sem laudo)
check = c.get(f"/api/c/{token}/documentos").json()
tipos = {s["tipo"] for s in check["slots"]}
assert "reservista" in tipos and "cert_casamento" in tipos and "cartao_vt" in tipos
assert "cert_nascimento_dep" in tipos and "cartao_vacina_dep" in tipos
assert "laudo_pcd" not in tipos and "declaracao_escolar_dep" not in tipos

# 9) upload: imagem vira PDF no MinIO; arquivo ruim é recusado com código
from datetime import date, timedelta

from PIL import ImageDraw


def _foto_nitida() -> bytes:
    """Foto de documento simulada: texto preto sobre branco (bordas nítidas
    passam na validação de nitidez, ao contrário de uma imagem lisa)."""
    im = Image.new("RGB", (900, 1200), "white")
    dr = ImageDraw.Draw(im)
    for i in range(28):
        dr.text((40, 30 + i * 40), f"REGISTRO GERAL 1234567 SSP-DF LINHA {i}", fill="black")
    b = io.BytesIO(); im.save(b, "JPEG")
    return b.getvalue()


def _pdf_texto(texto: str) -> bytes:
    from fpdf import FPDF
    p = FPDF(); p.add_page(); p.set_font("helvetica", size=12)
    p.multi_cell(0, 8, texto)
    return bytes(p.output())


slot_rg = next(s for s in check["slots"] if s["tipo"] == "rg")
r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("rg.jpg", _foto_nitida(), "image/jpeg")})
assert r.status_code == 200, r.text
assert r.json()["status"] == "enviado" and r.json()["paginas"] == 1

r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("x.txt", b"oi", "text/plain")})
assert r.status_code == 422 and r.json()["detail"] == "formato_nao_suportado"

# 9b) foto borrada/ilegível é recusada na hora
b = io.BytesIO(); Image.new("RGB", (900, 1200), "gray").save(b, "JPEG")
r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("borrada.jpg", b.getvalue(), "image/jpeg")})
assert r.status_code == 422 and r.json()["detail"] == "imagem_borrada", r.text

# 9c) comprovante de residência com mais de 90 dias é recusado; recente passa
slot_comp = next(s for s in check["slots"] if s["tipo"] == "comp_endereco")
antiga = (date.today() - timedelta(days=200)).strftime("%d/%m/%Y")
r = c.post(f"/api/c/{token}/documentos/{slot_comp['id']}/arquivo",
           files={"arquivo": ("conta.pdf",
                              _pdf_texto(f"CEB Conta de luz\nVencimento: {antiga}"),
                              "application/pdf")})
assert r.status_code == 422 and r.json()["detail"] == "comprovante_antigo", r.text
recente = (date.today() - timedelta(days=10)).strftime("%d/%m/%Y")
r = c.post(f"/api/c/{token}/documentos/{slot_comp['id']}/arquivo",
           files={"arquivo": ("conta.pdf",
                              _pdf_texto(f"CEB Conta de luz\nVencimento: {recente}"),
                              "application/pdf")})
assert r.status_code == 200, r.text

# 10) concluir envio antes da hora -> 422 com a lista do que falta
r = c.post(f"/api/c/{token}/concluir-envio")
assert r.status_code == 422 and len(r.json()["detail"]["faltando"]) > 0

# 11) envia todos os obrigatórios restantes e conclui
check = c.get(f"/api/c/{token}/documentos").json()
for s in check["slots"]:
    if s["obrigatorio"] and s["status"] == "pendente":
        rr = c.post(f"/api/c/{token}/documentos/{s['id']}/arquivo",
                    files={"arquivo": (f"{s['tipo']}.jpg", _foto_nitida(), "image/jpeg")})
        assert rr.status_code == 200, rr.text
r = c.post(f"/api/c/{token}/concluir-envio")
assert r.status_code == 200 and r.json()["status"] == "envio_concluido"

# 12) checklist congelado: novo upload é recusado
r = c.post(f"/api/c/{token}/documentos/{slot_rg['id']}/arquivo",
           files={"arquivo": ("rg2.jpg", _foto_nitida(), "image/jpeg")})
assert r.status_code == 409

# 13) RH revisa: rejeita o RG (candidato reabre), candidato reenvia, RH aprova tudo
detalhe = c.get(f"/api/rh/candidatos/{convite['candidato']['id']}", headers=rh).json()
slot_rg_rh = next(s for s in detalhe["slots"] if s["tipo"] == "rg")
r = c.post(f"/api/rh/slots/{slot_rg_rh['id']}/rejeitar", headers=rh,
           json={"motivo": "ilegivel"})
assert r.status_code == 200 and r.json()["status"] == "rejeitado"
estado = c.get(f"/api/c/{token}").json()
assert estado["status"] == "docs_pendentes"  # checklist reabriu para correção

r = c.post(f"/api/c/{token}/documentos/{slot_rg_rh['id']}/arquivo",
           files={"arquivo": ("rg-novo.jpg", _foto_nitida(), "image/jpeg")})
assert r.status_code == 200 and r.json()["status"] == "enviado"
assert c.post(f"/api/c/{token}/concluir-envio").status_code == 200

# dossiê antes de aprovar tudo -> 422 com pendências
r = c.post(f"/api/rh/candidatos/{convite['candidato']['id']}/dossie", headers=rh)
assert r.status_code == 422 and r.json()["detail"]["pendencias"]

detalhe = c.get(f"/api/rh/candidatos/{convite['candidato']['id']}", headers=rh).json()
for s in detalhe["slots"]:
    if s["status"] == "enviado":
        assert c.post(f"/api/rh/slots/{s['id']}/aprovar", headers=rh).status_code == 200

# 14) dossiê gerado na ordem oficial: 4 fichas assinadas + documentos aprovados
r = c.post(f"/api/rh/candidatos/{convite['candidato']['id']}/dossie", headers=rh)
assert r.status_code == 200 and r.json()["status"] == "aprovado", r.text
r = c.get(f"/api/rh/candidatos/{convite['candidato']['id']}/dossie", headers=rh)
assert r.status_code == 200 and r.content[:4] == b"%PDF"
from pypdf import PdfReader as _PR
paginas_dossie = len(_PR(io.BytesIO(r.content)).pages)
assert paginas_dossie >= 4 + 13, paginas_dossie  # 4 fichas + 13 docs deste candidato

# 15) expurgo: nada a expurgar dentro da retenção; forçando retenção 0 dias, expurga
import app.workers.expurgo as mod_exp
assert mod_exp.expurgar() == 0
from app.core.config import get_settings as _gs
_gs().retention_days = -1
assert mod_exp.expurgar() == 1
r = c.get(f"/api/rh/candidatos/{convite['candidato']['id']}/dossie", headers=rh)
assert r.status_code == 200  # dossiê final é preservado (registro trabalhista)

print("SMOKE TEST COMPLETO: 15/15 etapas ok")
