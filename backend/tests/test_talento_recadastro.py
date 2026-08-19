"""Recadastro no Banco de Talentos pela porta PÚBLICA (v3.05).

Feedback do Bruno (18/08/2026): *"pensar em uma hipótese da pessoa se cadastrar
apenas uma vez"*. A causa apurada: a porta do RH tinha dedup desde a v2.73
("avisa, não funde"), a importação de planilha também — e **a pública não tinha
nenhuma**. A mesma pessoa preenchendo duas vezes criava dois registros.

O que este teste protege:

1. **Não cria segundo registro** para a mesma pessoa (e-mail; ou nome+telefone).
2. **A resposta é IDÊNTICA** à de um cadastro novo. Esta rota é PÚBLICA: se ela
   dissesse "já existe", viraria uma sonda para descobrir quem está no banco de
   talentos digitando e-mails alheios — é o mesmo motivo pelo qual o gate do
   creche responde igual para CPF que existe e que não existe.
3. **Dado novo vale; campo vazio NÃO apaga o que havia.** Quem preenche de novo
   costuma preencher o essencial, e apagar o telefone que o RH já tinha seria
   perder dado por causa de um formulário mais curto.
4. **Arquivado volta para a fila** (decisão do Bruno) — e o motivo do
   arquivamento sobrevive, porque vive como anotação append-only no CRM.
5. **`convertido` NÃO é rebaixado**: a pessoa está em admissão, e voltá-la para
   "novo" a tiraria da fila onde está sendo admitida.

Precisa de banco. Roda no CI dentro do container da API.
"""
import os
import sys
import uuid as _uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.crm import Anotacao  # noqa: E402
from app.models.talento import StatusTalento, Talento  # noqa: E402

FALHAS = []
cli = TestClient(app, raise_server_exceptions=False)
db = SessionLocal()


def checar(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHA'}  {descricao}")
    if not condicao:
        FALHAS.append(descricao)


def _cadastrar(**kw):
    corpo = {"nome": "Fulano Recadastro", "consentimento_lgpd": True, **kw}
    return cli.post("/api/talentos", json=corpo)


def _quantos(email):
    db.expire_all()
    return db.scalar(select(func.count()).select_from(Talento).where(
        func.lower(Talento.email) == email.lower()))


print("1. o segundo cadastro NÃO cria um segundo registro")
email = f"recadastro-{_uuid.uuid4().hex[:8]}@exemplo.com.br"
r1 = _cadastrar(email=email, telefone="61999990000", cidade="Brasília")
checar(r1.status_code == 201, f"primeiro cadastro aceito (HTTP {r1.status_code})")
checar(_quantos(email) == 1, "um registro após o primeiro cadastro")

r2 = _cadastrar(email=email, telefone="61988887777", cidade="Taguatinga")
checar(r2.status_code == 201, f"segundo cadastro aceito (HTTP {r2.status_code})")
checar(_quantos(email) == 1, "CONTINUA um registro — não duplicou")

print("2. a resposta não revela que já existia (anti-enumeração)")
c1, c2 = r1.json(), r2.json()
checar(set(c1.keys()) == set(c2.keys()),
       f"mesmas chaves na resposta ({sorted(c1)} vs {sorted(c2)})")
checar(c2.get("ok") is True and bool(c2.get("upload_token")),
       "o recadastro também devolve ok + upload_token")
corpo_bruto = r2.text.lower()
for pista in ("existe", "duplicad", "ja_cadastrad", "recadastr"):
    checar(pista not in corpo_bruto, f"a resposta não contém a pista {pista!r}")

print("3. dado novo vale; campo vazio não apaga o que havia")
db.expire_all()
t = db.scalar(select(Talento).where(func.lower(Talento.email) == email.lower()))
checar(t.cidade == "Taguatinga", f"a cidade foi atualizada (veio {t.cidade})")
checar(t.telefone == "61988887777", "o telefone foi atualizado")
r3 = _cadastrar(email=email)          # sem telefone nem cidade
checar(r3.status_code == 201, "terceiro cadastro (sem os campos) aceito")
db.expire_all()
t = db.scalar(select(Talento).where(func.lower(Talento.email) == email.lower()))
checar(t.telefone == "61988887777",
       f"o telefone NÃO foi apagado pelo formulário vazio (veio {t.telefone})")
checar(t.cidade == "Taguatinga", "a cidade também não foi apagada")

print("4. quem estava ARQUIVADO volta para a fila")
t.status = StatusTalento.arquivado
db.commit()
r4 = _cadastrar(email=email)
checar(r4.status_code == 201, "recadastro de arquivado aceito")
db.expire_all()
t = db.scalar(select(Talento).where(func.lower(Talento.email) == email.lower()))
checar(t.status == StatusTalento.novo,
       f"voltou para 'novo' (veio {t.status.value if t.status else None})")
# o registro do que aconteceu tem que existir — senão o RH reavalia sem saber
notas = db.scalars(select(Anotacao).where(Anotacao.talento_id == t.id)).all()
checar(any("recadastr" in (n.texto or "").lower() for n in notas),
       "o recadastro ficou registrado no CRM")

print("5. quem já foi CONVERTIDO não é rebaixado")
# rebaixar tiraria da fila de admissão alguém que está sendo admitido
t.status = StatusTalento.convertido
db.commit()
r5 = _cadastrar(email=email)
checar(r5.status_code == 201, "recadastro de convertido aceito")
db.expire_all()
t = db.scalar(select(Talento).where(func.lower(Talento.email) == email.lower()))
checar(t.status == StatusTalento.convertido,
       f"continua convertido (veio {t.status.value if t.status else None})")

print("6. sem e-mail, casa por nome + telefone")
nome = f"Sem Email {_uuid.uuid4().hex[:6]}"
tel = "61977776666"
a = cli.post("/api/talentos", json={"nome": nome, "telefone": tel,
                                    "consentimento_lgpd": True})
b = cli.post("/api/talentos", json={"nome": nome, "telefone": tel,
                                    "consentimento_lgpd": True})
checar(a.status_code == 201 and b.status_code == 201, "os dois envios aceitos")
db.expire_all()
n = db.scalar(select(func.count()).select_from(Talento).where(
    func.lower(Talento.nome) == nome.lower()))
checar(n == 1, f"um registro só para nome+telefone iguais (encontrados {n})")

print()
if FALHAS:
    print(f"test_talento_recadastro: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_talento_recadastro: OK")
