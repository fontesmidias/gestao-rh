"""O anexo da entrevista — a dívida declarada da v2.64 (§ 5.3 do relatório).

Por que este teste existe: `POST/GET /rh/entrevistas/{id}/anexo` (cenário 20 do
`12-modulo-de-entrevistas.md` — currículo anotado, teste em papel fotografado)
foram entregues seguindo o padrão do `api/crm.py`, e o próprio relatório de
execução registrou a lacuna em vez de escondê-la na contagem:

    "5.3 Anexo sem teste automatizado — o cenário 20 está coberto por
     *código revisado*, não por teste."

Nesta casa isso é dívida real: quatro defeitos deste módulo passaram por revisão
de código e só caíram na MUTAÇÃO. O que o teste trava:

1. **A allowlist recusa o que não deve entrar.** `ext or "bin"` aceitando
   qualquer coisa foi o defeito do creche na v2.56 — e aqui a rota é do RH, mas
   o arquivo é servido de volta com `media_type` vindo do que foi gravado. É a
   armadilha do `marca.py` (v2.71): tirar formato perigoso da ENTRADA não basta
   se a SAÍDA continua servindo o que já entrou. Por isso o teste afirma sobre o
   `Content-Type` **da resposta**, não sobre a constante `ANEXO_CT`.

2. **O teto de tamanho vale.** Sem ele, o MinIO come 10MB por clique.

3. **`await arquivo.close()` no `finally`.** O Starlette faz spool em disco
   acima de ~1MB; sem fechar, sobra temporário no container (v2.56/v2.71). Como
   a rota é `async def` e o `TestClient` não expõe o `SpooledTemporaryFile`
   depois da resposta, a garantia aqui é ESTRUTURAL — `_tem_no_codigo` confere
   que o `close()` está no `finally` da rota, ignorando comentário e docstring
   (senão o teste casaria com o próprio texto que explica a correção — a
   armadilha do `test_upload_fecha_spool`).

4. **Trocar o anexo não deixa órfão no storage.** A rota remove a key anterior;
   sem isso, cada substituição acumula arquivo que ninguém mais alcança — e o
   expurgo não sabe dele, porque só o registro aponta para a key.

Mutações verificadas (todas reprovaram o código defeituoso):
  1. `if ext not in ANEXO_EXTS` removido            -> bloco 2 falha
  2. teto de tamanho removido                        -> bloco 3 falha
  3. `ct` chumbado em "application/pdf"              -> bloco 4 falha (era o
     defeito REAL do caminho do Graph, v2.68 — mesmo formato de erro)
  4. `storage.remover(e.anexo_key)` removido         -> bloco 5 falha
  5. `await arquivo.close()` retirado do `finally`   -> bloco 6 falha

Precisa dos containers de teste:
  docker run -d --name pg-teste ... postgres:16-alpine
  docker run -d --name minio-teste ... quay.io/minio/minio server /data

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_entrevista_anexo.py
"""

import os
import pathlib
import uuid

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

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entrevista import Entrevista  # noqa: E402
from app.services import storage  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[1]

c = TestClient(app)

# Credencial do AMBIENTE, nunca literal na linha do login: no CI o admin nasce
# com a senha do `.env` do job, e a literal devolvia 401 -> `KeyError: 'token'`,
# erro que não diz nada sobre a causa. Foi o que impediu dois testes de entrarem
# no CI (v2.71).
EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]

r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— num banco com usuários antigos o admin do .env não existe, porque "
    f"`criar_admin_inicial` só cria com a tabela vazia. Resposta: {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

# Sufixo por EXECUÇÃO: e-mail de talento é único, e teste que só passa em banco
# limpo é armadilha (v2.14).
SUF = uuid.uuid4().hex[:8]

falhas: list[str] = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def _tem_no_codigo(texto: str, trecho: str) -> bool:
    """O trecho aparece numa linha de CÓDIGO (não em comentário nem docstring).

    Sem isto, procurar `arquivo.close()` casaria com o comentário que EXPLICA a
    garantia — o teste aprovaria a documentação em vez do código, e o reflexo de
    quem quebrasse a rota seria apagar o comentário.
    """
    dentro_docstring = False
    for linha in texto.splitlines():
        nua = linha.strip()
        aspas = nua.count('"""') + nua.count("'''")
        if aspas:
            # Docstring de uma linha só (abre e fecha) não muda o estado.
            if aspas % 2 == 1:
                dentro_docstring = not dentro_docstring
            continue
        if dentro_docstring or nua.startswith("#"):
            continue
        codigo = linha.split("#", 1)[0]
        if trecho in codigo:
            return True
    return False


def criar_entrevista() -> str:
    r = c.post("/api/talentos", json={
        "nome": "Anexo de Teste",
        "email": f"anexo-{SUF}-{uuid.uuid4().hex[:6]}@exemplo.com",
        "telefone": "61999990000", "cargos_interesse": ["Vigia"],
        "consentimento_lgpd": True})
    assert r.status_code in (200, 201), f"criar talento: {r.status_code} {r.text}"
    talento_id = r.json()["id"]
    r = c.post("/api/rh/entrevistas", headers=RH,
               json={"talento_id": talento_id, "tipo": "entrevista"})
    assert r.status_code in (200, 201), f"criar entrevista: {r.status_code} {r.text}"
    return r.json()["id"]


# --------------------------------------------------------------------------
print("\n1. o anexo sobe, fica no registro e volta pelo GET")
# --------------------------------------------------------------------------
ent = criar_entrevista()

r = c.post(f"/api/rh/entrevistas/{ent}/anexo", headers=RH,
           files={"arquivo": ("curriculo-anotado.pdf", b"%PDF-1.4 conteudo",
                              "application/pdf")})
checar(r.status_code == 200, "POST /anexo com .pdf responde 200")
checar((r.json() or {}).get("anexo_nome") == "curriculo-anotado.pdf",
       "o nome do arquivo volta no dump da entrevista")

r = c.get(f"/api/rh/entrevistas/{ent}/anexo", headers=RH)
checar(r.status_code == 200, "GET /anexo devolve o arquivo")
checar(r.content == b"%PDF-1.4 conteudo",
       "o conteúdo que volta é BYTE A BYTE o que subiu")

# --------------------------------------------------------------------------
print("\n2. a allowlist recusa formato fora da lista")
# --------------------------------------------------------------------------
# ⚠️ Mutação 1: remover `if ext not in ANEXO_EXTS` -> estas 3 asserções falham.
for nome, ct in [("payload.exe", "application/octet-stream"),
                 ("logo.svg", "image/svg+xml"),
                 ("sem-extensao", "application/octet-stream")]:
    r = c.post(f"/api/rh/entrevistas/{ent}/anexo", headers=RH,
               files={"arquivo": (nome, b"conteudo qualquer", ct)})
    checar(r.status_code == 422,
           f"{nome} é recusado com 422 (não entra no storage)")

# O SVG merece a sua linha: é código que executa no navegador de quem está
# logado, e o anexo é servido inline com o Content-Type do que foi gravado —
# seria XSS armazenado, o defeito do `marca.py` na v2.71.

# --------------------------------------------------------------------------
print("\n3. o teto de tamanho vale")
# --------------------------------------------------------------------------
# ⚠️ Mutação 2: remover a checagem de `ANEXO_MAX_BYTES` -> esta asserção falha.
gigante = b"x" * (10 * 1024 * 1024 + 1)
r = c.post(f"/api/rh/entrevistas/{ent}/anexo", headers=RH,
           files={"arquivo": ("grande.pdf", gigante, "application/pdf")})
checar(r.status_code == 413,
       "arquivo acima de 10MB é recusado com 413 (não ocupa o MinIO)")

# --------------------------------------------------------------------------
print("\n4. o Content-Type que VOLTA descreve o arquivo, não um chumbado")
# --------------------------------------------------------------------------
# ⚠️ Mutação 3: `ct = "application/pdf"` chumbado -> as 2 asserções falham.
#
# A asserção é sobre a RESPOSTA do GET, não sobre a constante `ANEXO_CT`:
# afirmar `ANEXO_CT["png"] == "image/png"` testaria o dicionário, não a
# LIGAÇÃO — e foi exatamente assim que o `application/pdf` chumbado do caminho
# do Graph sobreviveu até a v2.68, com o teste verde ao lado.
ent_png = criar_entrevista()
r = c.post(f"/api/rh/entrevistas/{ent_png}/anexo", headers=RH,
           files={"arquivo": ("foto-do-teste.png", b"\x89PNG\r\n\x1a\n", "image/png")})
checar(r.status_code == 200, "POST /anexo com .png responde 200")

r = c.get(f"/api/rh/entrevistas/{ent_png}/anexo", headers=RH)
checar(r.headers.get("content-type", "").startswith("image/png"),
       "o GET devolve image/png — o tipo descreve o arquivo REAL")

# --------------------------------------------------------------------------
print("\n5. trocar o anexo não deixa órfão no storage")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4: remover o `storage.remover(e.anexo_key)` -> a 2ª asserção falha.
#
# Órfão no MinIO é invisível: só o registro aponta para a key, então o arquivo
# antigo deixa de ser alcançável por qualquer tela E por qualquer expurgo.
ent_troca = criar_entrevista()
c.post(f"/api/rh/entrevistas/{ent_troca}/anexo", headers=RH,
       files={"arquivo": ("primeiro.pdf", b"primeiro", "application/pdf")})
with SessionLocal() as db:
    key_antiga = db.get(Entrevista, uuid.UUID(ent_troca)).anexo_key

c.post(f"/api/rh/entrevistas/{ent_troca}/anexo", headers=RH,
       files={"arquivo": ("segundo.png", b"\x89PNG-segundo", "image/png")})
with SessionLocal() as db:
    key_nova = db.get(Entrevista, uuid.UUID(ent_troca)).anexo_key

checar(key_nova != key_antiga, "a key muda quando a extensão muda (.pdf -> .png)")

sumiu = False
try:
    storage.ler(key_antiga)
except Exception:
    sumiu = True
checar(sumiu, "o arquivo ANTERIOR foi removido do storage (não virou órfão)")

r = c.get(f"/api/rh/entrevistas/{ent_troca}/anexo", headers=RH)
checar(r.content == b"\x89PNG-segundo", "o GET passa a servir o arquivo novo")

# --------------------------------------------------------------------------
print("\n6. o spool é fechado — garantia ESTRUTURAL")
# --------------------------------------------------------------------------
# ⚠️ Mutação 5: tirar `await arquivo.close()` do `finally` -> falha.
#
# O `TestClient` não expõe o `SpooledTemporaryFile` depois que a resposta volta,
# então não dá para afirmar sobre o objeto real como o `test_upload_fecha_spool`
# faz. A garantia aqui é a MESMA do teste de `marca.py`: o `close()` está numa
# linha de CÓDIGO da rota, dentro do `finally` — comentário não conta.
fonte = (RAIZ / "app" / "api" / "entrevistas.py").read_text(encoding="utf-8")
checar(_tem_no_codigo(fonte, "await arquivo.close()"),
       "a rota de anexo fecha o upload em CÓDIGO (não só no comentário)")

trecho_anexo = fonte.split('@router.post("/rh/entrevistas/{entrevista_id}/anexo")')
tem_finally = len(trecho_anexo) > 1 and "finally:" in trecho_anexo[1][:2000]
checar(tem_finally,
       "o close() está num `finally` — fecha mesmo quando o 413 levanta no meio")

# --------------------------------------------------------------------------
print("\n7. entrevista inexistente não vaza nem cria")
# --------------------------------------------------------------------------
fantasma = uuid.uuid4()
r = c.post(f"/api/rh/entrevistas/{fantasma}/anexo", headers=RH,
           files={"arquivo": ("x.pdf", b"x", "application/pdf")})
checar(r.status_code == 404, "POST /anexo em entrevista inexistente dá 404")

r = c.get(f"/api/rh/entrevistas/{fantasma}/anexo", headers=RH)
checar(r.status_code == 404, "GET /anexo em entrevista inexistente dá 404")

ent_sem = criar_entrevista()
r = c.get(f"/api/rh/entrevistas/{ent_sem}/anexo", headers=RH)
checar(r.status_code == 404,
       "GET /anexo de entrevista SEM anexo dá 404 (não devolve corpo vazio 200)")

# --------------------------------------------------------------------------
print("\n8. a rota exige RH — o anexo não é público")
# --------------------------------------------------------------------------
r = c.get(f"/api/rh/entrevistas/{ent}/anexo")
checar(r.status_code in (401, 403),
       "GET /anexo sem token é recusado (currículo anotado não é público)")


print()
if falhas:
    print(f"test_entrevista_anexo: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_entrevista_anexo: OK")
