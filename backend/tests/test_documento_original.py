"""O candidato vê o ORIGINAL que enviou, não o PDF timbrado (v2.35).

`/c/{token}/documentos/{id}/arquivo` sempre serviu o PDF que o sistema monta: a
foto reduzida e centralizada numa página A4 no papel timbrado. Para o dossiê do
RH está certo. Para alguém conferir se a PRÓPRIA foto saiu legível antes de
concluir o envio, é o documento errado — a miniatura faz uma foto boa parecer
ruim, e uma ruim parecer aceitável.

O que este teste protege:

1. **O original é o original** — `/original/1` devolve os MESMOS bytes que
   subiram, com Content-Type de imagem; `/arquivo` continua devolvendo o PDF.
   São arquivos diferentes, e é o ponto todo da entrega.
2. **Frente e verso são arquivos DISTINTOS** — o registro guarda a key de um só
   (`arquivo_original_key`, o primeiro), então servir "o original" pelo campo
   do banco mostraria a frente duas vezes e diria que aquilo é o envio inteiro.
3. **A ordem é numérica, não lexicográfica** — com 10 partes, o `listar` do
   storage devolve "10-" antes de "2-", e o verso apareceria no lugar da
   frente.
4. **O documento é do dono** — token de outro candidato não alcança o slot.
5. **Expurgo apaga TODAS as partes** (LGPD): o defeito que este teste fixa
   deixava o VERSO no MinIO para sempre, sem nenhuma tela onde notar a sobra.
6. **Formato que o navegador não exibe é convertido, e falha de conversão não
   deixa a pessoa sem o arquivo** — degrada para download, nunca 500.

Precisa dos containers de teste (pg-teste/minio-teste).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_documento_original.py
"""

import io
import os
import uuid

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
from PIL import Image, ImageDraw  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.api.documentos import _originais_do_slot, _resposta_exibivel  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.documento import SlotDocumento  # noqa: E402
from app.services import storage  # noqa: E402
from app.workers.expurgo import _arquivos_do_slot  # noqa: E402

c = TestClient(app)


def _nitida(texto: str) -> bytes:
    """Imagem lisa é recusada com 422 imagem_borrada — precisa de bordas.
    O `texto` muda os bytes: é assim que se prova que frente e verso não são o
    mesmo arquivo servido duas vezes."""
    im = Image.new("RGB", (900, 1200), "white")
    dr = ImageDraw.Draw(im)
    for i in range(28):
        dr.text((40, 30 + i * 40), f"{texto} 1234567 SSP-DF LINHA {i}", fill="black")
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


rh = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}
jid = c.post("/api/rh/jornadas", headers=rh,
             json={"descricao": f"ORIGINAL - TESTE {uuid.uuid4().hex[:6]}"}).json()["id"]


def _candidato() -> str:
    r = c.post("/api/rh/candidatos", headers=rh, json={
        "nome_completo": "Ana Original Teste",
        "email": f"ana.original.{uuid.uuid4().hex[:8]}@example.com",
        "celular_whatsapp": "+5561999995555", "jornada_id": jid,
        "cargo_funcao": "Auxiliar de Serviços Gerais"})
    tok = r.json()["link_magico"].rsplit("/c/", 1)[1]
    c.post(f"/api/c/{tok}/aceite", json={"aceite_lgpd": True})
    return tok


def _slot_simples(tok: str) -> dict:
    """Um slot obrigatório pendente, evitando os que têm tratamento especial:
    `comp_endereco` roda OCR bloqueante e `cpf_doc` confere o CPF no texto."""
    slots = c.get(f"/api/c/{tok}/documentos").json()["slots"]
    return next(s for s in slots
                if s["obrigatorio"] and s["status"] == "pendente"
                and s["tipo"] not in ("comp_endereco", "cpf_doc"))


# ============================================ 1. original != PDF timbrado
tok = _candidato()
slot = _slot_simples(tok)
FRENTE, VERSO = _nitida("FRENTE DO DOCUMENTO"), _nitida("VERSO DO DOCUMENTO")
assert FRENTE != VERSO

r = c.post(f"/api/c/{tok}/documentos/{slot['id']}/arquivo", files=[
    ("arquivos", ("frente.jpg", FRENTE, "image/jpeg")),
    ("arquivos", ("verso.jpg", VERSO, "image/jpeg")),
])
assert r.status_code == 200, r.text

r = c.get(f"/api/c/{tok}/documentos/{slot['id']}/originais")
assert r.status_code == 200, r.text
lista = r.json()
assert [a["indice"] for a in lista["arquivos"]] == [1, 2], (
    "as DUAS partes enviadas têm que aparecer — dizer 'é isto que você enviou' "
    f"mostrando só a frente é mentira: {lista}")
assert [a["nome"] for a in lista["arquivos"]] == ["frente.jpg", "verso.jpg"], lista
assert lista["tem_pdf"] is True, lista

r1 = c.get(f"/api/c/{tok}/documentos/{slot['id']}/original/1")
assert r1.status_code == 200, r1.text
assert r1.content == FRENTE, (
    "o original tem que sair EXATAMENTE como a pessoa enviou — se vier o PDF "
    "timbrado, ela não consegue julgar a própria foto")
assert r1.headers["content-type"].startswith("image/jpeg"), r1.headers
assert "inline" in r1.headers.get("content-disposition", ""), r1.headers

r2 = c.get(f"/api/c/{tok}/documentos/{slot['id']}/original/2")
assert r2.status_code == 200 and r2.content == VERSO, (
    "o verso tem que ser o VERSO — servir a key do registro devolveria a "
    "frente duas vezes")

pdf = c.get(f"/api/c/{tok}/documentos/{slot['id']}/arquivo")
assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), pdf.headers
assert pdf.content not in (FRENTE, VERSO), (
    "o PDF do RH e o original são documentos diferentes — se fossem iguais, "
    "não haveria o que corrigir aqui")

# índice que não existe não devolve arquivo de ninguém
assert c.get(f"/api/c/{tok}/documentos/{slot['id']}/original/99").status_code == 404
assert c.get(f"/api/c/{tok}/documentos/{slot['id']}/original/0").status_code == 404

# ================================================ 2. o documento é do dono
outro = _candidato()
r = c.get(f"/api/c/{outro}/documentos/{slot['id']}/originais")
assert r.status_code == 404 and r.json()["detail"] == "slot_nao_encontrado", (
    f"o token de um candidato não pode alcançar o slot de outro: {r.text}")
r = c.get(f"/api/c/{outro}/documentos/{slot['id']}/original/1")
assert r.status_code == 404, r.text

# ======================================== 3. ordem numérica, não de texto
with SessionLocal() as db:
    obj = db.scalars(select(SlotDocumento)
                     .where(SlotDocumento.id == uuid.UUID(slot["id"]))).one()
    base = f"candidatos/{obj.candidato_id}/slots/{obj.id}/original/"
    for i in range(3, 12):                      # já existem 1 e 2
        storage.salvar(f"{base}{i}-pagina.jpg", f"pagina {i}".encode(), "image/jpeg")
    ordem = [i for i, _, _ in _originais_do_slot(obj)]
assert ordem == list(range(1, 12)), (
    "a ordem é a do ENVIO, pelo número do prefixo; a lexicográfica do storage "
    f"põe '10-' antes de '2-' e troca a frente pelo verso: {ordem}")

r = c.get(f"/api/c/{tok}/documentos/{slot['id']}/originais")
assert [a["indice"] for a in r.json()["arquivos"]] == list(range(1, 12)), r.text
assert c.get(f"/api/c/{tok}/documentos/{slot['id']}/original/10").content == b"pagina 10"

# ================================= 4. expurgo leva TODAS as partes (LGPD)
with SessionLocal() as db:
    obj = db.scalars(select(SlotDocumento)
                     .where(SlotDocumento.id == uuid.UUID(slot["id"]))).one()
    do_expurgo = set(_arquivos_do_slot(obj))
    no_storage = set(storage.listar(f"candidatos/{obj.candidato_id}/slots/{obj.id}/"))
    key_do_registro = obj.arquivo_original_key
assert do_expurgo == no_storage, (
    "o expurgo tem que varrer o slot inteiro; pelas duas keys do registro o "
    f"VERSO ficaria no MinIO para sempre: sobraria {no_storage - do_expurgo}")
assert len(do_expurgo) > 2 and key_do_registro in do_expurgo, do_expurgo

# =============================== 5. conversão de exibição, e falha degrada
resp = _resposta_exibivel("foto.jpg", FRENTE)
assert resp.media_type == "image/jpeg" and resp.body == FRENTE, (
    "imagem que o navegador exibe não passa por conversão nenhuma")

import app.services.normalizacao as _norm  # noqa: E402

_original_word = _norm._word_para_pdf
try:
    _norm._word_para_pdf = lambda ext, dados: b"%PDF-convertido"
    resp = _resposta_exibivel("curriculo.docx", b"PK\x03\x04-falso")
    assert resp.media_type == "application/pdf", (
        "Word é convertido ao SERVIR — navegador nenhum renderiza .docx, e a "
        "aba em branco parece defeito do sistema")
    assert "inline" in resp.headers["content-disposition"], resp.headers

    def _explode(ext, dados):
        raise RuntimeError("libreoffice fora do ar")

    _norm._word_para_pdf = _explode
    resp = _resposta_exibivel("curriculo.docx", b"PK\x03\x04-falso")
    assert resp.status_code == 200 and resp.body == b"PK\x03\x04-falso", (
        "conversão que falha não pode deixar a pessoa sem o arquivo")
    assert "attachment" in resp.headers["content-disposition"], (
        "sem poder exibir, o arquivo BAIXA — `inline` num tipo que o navegador "
        f"não renderiza abre aba em branco: {resp.headers}")
finally:
    _norm._word_para_pdf = _original_word

# ============ 6. fallback: storage não lista, mas o registro tem uma key
solto = SlotDocumento(id=uuid.uuid4(), candidato_id=uuid.uuid4())
solto.arquivo_original_key = (
    f"candidatos/{solto.candidato_id}/slots/{solto.id}/original/1-doc-frente.jpg")
assert _originais_do_slot(solto) == [(1, "doc-frente.jpg", solto.arquivo_original_key)], (
    "sem listagem no storage, o registro ainda serve o primeiro arquivo — e o "
    "nome sai inteiro: cortar no último hífen viraria 'frente.jpg'")

# ==================== 7. envio antigo sem originais: o PDF ainda responde
with SessionLocal() as db:
    obj = db.scalars(select(SlotDocumento)
                     .where(SlotDocumento.id == uuid.UUID(slot["id"]))).one()
    for key in storage.listar(f"candidatos/{obj.candidato_id}/slots/{obj.id}/original/"):
        storage.remover(key)
    obj.arquivo_original_key = None
    db.commit()

r = c.get(f"/api/c/{tok}/documentos/{slot['id']}/originais")
assert r.status_code == 200 and r.json()["arquivos"] == [] and r.json()["tem_pdf"], (
    "sem original guardado a lista vem VAZIA e o PDF continua lá — é o que "
    f"faz a tela cair no PDF em vez de quebrar: {r.text}")
assert c.get(f"/api/c/{tok}/documentos/{slot['id']}/arquivo").status_code == 200

print("test_documento_original: OK")
