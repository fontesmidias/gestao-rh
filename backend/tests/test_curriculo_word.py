"""Currículo em Word abre NA TELA, convertido (v2.33).

Pedido do Bruno em 2026-07-30: *"seria interessante que não baixasse
necessariamente o currículo, mas que tivesse opção para renderizar o currículo
na tela"* — e, perguntado sobre o Word (que navegador nenhum renderiza), ele
escolheu **converter**.

O que este teste protege:

1. **Word vira PDF ao SERVIR** — `Content-Type: application/pdf` e `inline`.
   Sem isso, a aba abria em branco (defeito real da v2.11): o arquivo estava
   certo, o navegador é que não exibe `.docx`.
2. **O ORIGINAL continua guardado** no MinIO. A conversão é de EXIBIÇÃO; o
   currículo é documento de terceiro e o que a pessoa enviou não se altera.
3. **Falha de conversão não deixa o RH sem o arquivo** — degrada para servir o
   original (baixar), nunca 500.
4. **PDF e imagem seguem intactos** — não podem passar pelo LibreOffice à toa.

Precisa dos containers de teste (pg-teste/minio-teste).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_curriculo_word.py
"""

import os
import uuid

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import talentos as api_talentos  # noqa: E402
from app.api.talentos import _ehWord  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.talento import Talento  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.services import storage  # noqa: E402
from sqlalchemy import select  # noqa: E402

c = TestClient(app)

# ------------------------------------------------- detecção (unitária)
assert _ehWord("cv.docx", None) is True
assert _ehWord("cv.doc", "application/octet-stream") is True, (
    "upload de celular chega como octet-stream — só o NOME denuncia o Word")
assert _ehWord(None, "application/msword") is True
assert _ehWord("cv.pdf", "application/pdf") is False
assert _ehWord("foto.jpg", "image/jpeg") is False
assert _ehWord(None, None) is False

# ------------------------------------------------------------- arranjo
EMAIL = f"rh-word-{uuid.uuid4().hex[:8]}@exemplo.com"
SENHA = "teste-word-123"
with SessionLocal() as db:
    db.add(UsuarioRH(email=EMAIL, nome="RH Teste Word",
                     senha_hash=hash_senha(SENHA), ativo=True))
    db.commit()

tok = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}

DOCX_BYTES = b"PK\x03\x04-conteudo-falso-de-docx"


def _talento_com_curriculo(nome_arq: str, ct: str, dados: bytes) -> uuid.UUID:
    with SessionLocal() as db:
        t = Talento(nome="Fulano do Teste", email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                    cargo_interesse="analista")
        db.add(t)
        db.flush()
        key = f"talentos/{t.id}/curriculo{os.path.splitext(nome_arq)[1]}"
        storage.salvar(key, dados, ct)
        t.curriculo_key, t.curriculo_nome, t.curriculo_tipo = key, nome_arq, ct
        db.commit()
        return t.id, key


# ---------------------------------------- 1) Word convertido + 2) original
tid, key = _talento_com_curriculo("curriculo.docx", "application/octet-stream", DOCX_BYTES)

_pdf_falso = b"%PDF-1.4\n%falso\n"
_orig_conv = None
try:
    from app.services import normalizacao
    _orig_conv = normalizacao._word_para_pdf
    normalizacao._word_para_pdf = lambda ext, dados: _pdf_falso

    r = c.get(f"/api/rh/talentos/{tid}/curriculo", headers=H)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/pdf"), (
        f"Word tem que ser servido como PDF, veio {r.headers['content-type']} — "
        f"senão a aba abre EM BRANCO (defeito da v2.11)")
    assert "inline" in r.headers.get("content-disposition", ""), (
        "convertido para PDF, tem que abrir na tela e não baixar")
    assert r.content == _pdf_falso
    assert ".pdf" in r.headers.get("content-disposition", ""), (
        "o nome oferecido tem que acompanhar o formato servido")

    # 2) o ORIGINAL continua guardado: conversão é de EXIBIÇÃO
    assert storage.ler(key) == DOCX_BYTES, (
        "o arquivo no storage foi alterado — o currículo é documento de "
        "terceiro e tem que ficar como a pessoa enviou")
finally:
    if _orig_conv is not None:
        normalizacao._word_para_pdf = _orig_conv

# ---------------------------------------- 3) conversão falha → serve original
def _explode(ext, dados):
    raise RuntimeError("libreoffice fora do ar")


_orig_conv = normalizacao._word_para_pdf
normalizacao._word_para_pdf = _explode
try:
    r = c.get(f"/api/rh/talentos/{tid}/curriculo", headers=H)
    assert r.status_code == 200, (
        f"conversão falhou e a rota devolveu {r.status_code} — o RH ficaria sem "
        f"o currículo por causa de um conversor fora do ar")
    assert r.content == DOCX_BYTES, "deveria degradar servindo o original"
    assert "attachment" in r.headers.get("content-disposition", ""), (
        "sem conversão, o Word tem que BAIXAR — inline abriria aba em branco")
finally:
    normalizacao._word_para_pdf = _orig_conv

# ---------------------------------------- 4) PDF e imagem não são tocados
tid_pdf, _ = _talento_com_curriculo("cv.pdf", "application/pdf", b"%PDF-1.4\noriginal\n")
r = c.get(f"/api/rh/talentos/{tid_pdf}/curriculo", headers=H)
assert r.status_code == 200 and r.content == b"%PDF-1.4\noriginal\n", r.status_code
assert "inline" in r.headers.get("content-disposition", "")

tid_img, _ = _talento_com_curriculo("foto.jpg", "image/jpeg", b"\xff\xd8\xff-jpeg-falso")
r = c.get(f"/api/rh/talentos/{tid_img}/curriculo", headers=H)
assert r.status_code == 200 and r.content == b"\xff\xd8\xff-jpeg-falso"
assert r.headers["content-type"].startswith("image/"), (
    "imagem não pode passar pelo conversor de Word")

# ------------------------------------------------------------- limpeza
with SessionLocal() as db:
    for t in db.scalars(select(Talento).where(Talento.id.in_([tid, tid_pdf, tid_img]))).all():
        db.delete(t)
    u = db.scalar(select(UsuarioRH).where(UsuarioRH.email == EMAIL))
    if u:
        db.delete(u)
    db.commit()

print("test_curriculo_word: OK")
