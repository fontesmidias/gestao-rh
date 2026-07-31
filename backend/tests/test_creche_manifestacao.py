"""Manifestação ativa no levantamento do creche (v2.34).

Pedido do Bruno em 2026-07-30:

    *"eu quero fazer um movimento que a pessoa manifeste que de fato tem ou não
    tem crianças, e não simplesmente a pessoa entra no link e, como não tem,
    não faz nada e sai. E hoje a pessoa pode não ter filhos, mas amanhã pode
    ter — então é importante deixar tudo bem registrado."*

A diferença é jurídica, não cosmética: sem manifestação, **"não respondeu" e
"não tem direito" são a mesma linha em branco** na planilha do RH, e daqui a
dois anos ninguém consegue demonstrar que o elegível foi consultado.

O que este teste protege:

1. **Declarar registra quem, quando e por qual caminho** — é o que sustenta a
   prova se ela for contestada.
2. **Quem tem criança cadastrada NÃO declara que não tem** (409): o registro
   não pode contradizer o dado ao lado dele.
3. **A declaração é reversível** — quem passa a ter filho volta pelo `/reabrir`.
   Declarar hoje não pode fechar a porta amanhã.
4. **O quadro da consulta fecha**: elegíveis, responderam, faltam. E "declarou
   que não tem" CONTA como resposta — a manifestação é o que se prova, não o
   pedido. Um levantamento aberto e nunca enviado NÃO conta.

Precisa dos containers de teste (pg-teste/minio-teste).
Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_creche_manifestacao.py
"""

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
os.environ.setdefault("MINIO_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.api.creche_publico import _hash  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.main import app  # noqa: E402
from app.models.beneficio import (AcessoCreche, BeneficioCreche,  # noqa: E402
                                  StatusBeneficio)
from app.models.candidato import (Candidato, PostoServico,  # noqa: E402
                                  SituacaoColaborador)
from app.models.evento import EventoAuditoria  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402

c = TestClient(app)


def _cpf_novo() -> str:
    base = [int(x) for x in f"{secrets.randbelow(10**9):09d}"]
    for _ in range(2):
        peso = len(base) + 1
        s = sum(v * (peso - i) for i, v in enumerate(base))
        d = (s * 10) % 11
        base.append(0 if d == 10 else d)
    return "".join(map(str, base))


SUF = uuid.uuid4().hex[:8]
with SessionLocal() as db:
    posto = PostoServico(nome=f"POSTO MANIFESTACAO {SUF}", da_direito_creche=True,
                         valor_reembolso_creche="500,00")
    db.add(posto)
    db.flush()
    posto_id = posto.id
    db.commit()


def _colaborador(nome: str) -> uuid.UUID:
    with SessionLocal() as db:
        col = Candidato(nome_completo=nome, cpf=_cpf_novo(),
                        email=f"{uuid.uuid4().hex[:8]}@exemplo.com",
                        situacao=SituacaoColaborador.ativo,
                        posto_servico_id=posto_id)
        db.add(col)
        db.commit()
        return col.id


def _sessao(col_id: uuid.UUID) -> str:
    """Sessão de creche já confirmada, como depois do 2FA."""
    token = secrets.token_urlsafe(32)
    agora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        ben = db.scalar(select(BeneficioCreche).where(
            BeneficioCreche.candidato_id == col_id))
        if ben is None:
            ben = BeneficioCreche(candidato_id=col_id,
                                  status=StatusBeneficio.levantamento)
            db.add(ben)
            db.flush()
        db.add(AcessoCreche(beneficio_id=ben.id, token_hash=_hash(token),
                            confirmado_em=agora,
                            expira_em=agora + timedelta(hours=6)))
        db.commit()
    return token


# ------------------------------------ 1) declarar registra o rastro
col_a = _colaborador(f"Ana Sem Filhos {SUF}")
tok_a = _sessao(col_a)

r = c.post(f"/api/creche/sessao/{tok_a}/sem-direito")
assert r.status_code == 200, r.text
assert r.json()["status"] == "sem_direito_declarado", r.json()

with SessionLocal() as db:
    ben = db.scalar(select(BeneficioCreche).where(BeneficioCreche.candidato_id == col_a))
    assert ben.status == StatusBeneficio.sem_direito_declarado
    assert ben.sem_direito_em is not None, "sem QUANDO a declaração não prova nada"
    assert ben.sem_direito_por == "colaborador", (
        "tem que registrar que foi a PRÓPRIA pessoa — o RH também pode marcar, "
        "e os dois casos não valem a mesma coisa numa contestação")
    ev = db.scalars(select(EventoAuditoria).where(
        EventoAuditoria.acao == "creche_sem_direito",
        EventoAuditoria.candidato_id == col_a)).all()
    assert ev, "declaração sem auditoria não é prova de consulta"
    assert (ev[0].detalhe or {}).get("por") == "colaborador", ev[0].detalhe

# ------------------------------------ 2) com criança cadastrada, NÃO declara
col_b = _colaborador(f"Bruno Com Filho {SUF}")
tok_b = _sessao(col_b)
r = c.post(f"/api/creche/sessao/{tok_b}/criancas",
           json={"nome": "Filho do Bruno", "data_nascimento": "2023-05-10",
                 "parentesco": "filho"})
assert r.status_code in (200, 201), r.text

r = c.post(f"/api/creche/sessao/{tok_b}/sem-direito")
assert r.status_code == 409, (
    f"quem cadastrou criança não pode declarar que não tem nenhuma (veio "
    f"{r.status_code}) — o registro contradiria o dado ao lado dele")
assert r.json()["detail"] == "ha_criancas_cadastradas", r.json()
with SessionLocal() as db:
    ben = db.scalar(select(BeneficioCreche).where(BeneficioCreche.candidato_id == col_b))
    assert ben.status == StatusBeneficio.levantamento, "o status não podia mudar"

# ------------------------------------ 3) declarar duas vezes é recusado
r = c.post(f"/api/creche/sessao/{tok_a}/sem-direito")
assert r.status_code == 409, "já declarado tem que recusar, não reescrever a data"

# ------------------------------------ 4) o quadro da consulta fecha
EMAIL = f"rh-manifesto-{SUF}@exemplo.com"
with SessionLocal() as db:
    db.add(UsuarioRH(email=EMAIL, nome="RH Manifesto",
                     senha_hash=hash_senha("manifesto-123"), ativo=True))
    db.commit()
tok_rh = c.post("/api/rh/auth/login",
                json={"email": EMAIL, "senha": "manifesto-123"}).json()["token"]
H = {"Authorization": f"Bearer {tok_rh}"}

# uma terceira pessoa que NÃO respondeu (nem abriu o link)
col_c = _colaborador(f"Carla Nao Respondeu {SUF}")

resumo = c.get("/api/rh/creche/resumo", headers=H).json()
for campo in ("responderam", "declararam_sem_direito", "faltam_responder"):
    assert campo in resumo, f"o resumo precisa de '{campo}' para o quadro fechar"

# do NOSSO posto: 3 elegíveis (a=declarou, b=abriu e parou, c=nem abriu)
pend = c.get("/api/rh/creche/pendentes-resposta", headers=H).json()
ids_pend = {p["candidato_id"] for p in pend}
assert str(col_c) in {str(i) for i in ids_pend}, (
    "quem nunca abriu o link tem que aparecer como pendente")
assert str(col_b) in {str(i) for i in ids_pend}, (
    "quem abriu e parou no meio NÃO respondeu — levantamento nunca enviado não "
    "pode contar como manifestação")
assert str(col_a) not in {str(i) for i in ids_pend}, (
    "quem DECLAROU que não tem direito respondeu — some da fila de cobrança, "
    "mas continua no relatório como consultado")

# ------------------------------------ 5) reversível: o RH reabre
r = c.post(f"/api/rh/creche/levantamentos/"
           f"{c.get('/api/rh/creche/levantamentos?status=sem_direito_declarado', headers=H).json()[0]['id']}"
           f"/reabrir", headers=H)
assert r.status_code == 200, (
    f"declaração tem que ser reversível — quem passa a ter filho amanhã não "
    f"pode ficar preso na resposta de hoje ({r.text})")

# ------------------------------------------------------------- limpeza
with SessionLocal() as db:
    for cid in (col_a, col_b, col_c):
        for b in db.scalars(select(BeneficioCreche).where(
                BeneficioCreche.candidato_id == cid)).all():
            for ac in db.scalars(select(AcessoCreche).where(
                    AcessoCreche.beneficio_id == b.id)).all():
                db.delete(ac)
            for k in list(b.criancas):
                db.delete(k)
            db.delete(b)
        for e in db.scalars(select(EventoAuditoria).where(
                EventoAuditoria.candidato_id == cid)).all():
            db.delete(e)
        # flush ANTES de apagar o candidato: a auditoria tem FK para ele, e sem
        # isto o SQLAlchemy ordena os DELETEs ao contrário e estoura FK.
        db.flush()
        col = db.get(Candidato, cid)
        if col:
            db.delete(col)
            db.flush()
    u = db.scalar(select(UsuarioRH).where(UsuarioRH.email == EMAIL))
    if u:
        db.delete(u)
    p = db.get(PostoServico, posto_id)
    if p:
        db.delete(p)
    db.commit()

print("test_creche_manifestacao: OK")
