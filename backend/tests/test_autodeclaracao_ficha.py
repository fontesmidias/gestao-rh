"""A autodeclaração de residência tem porta na FICHA (v3.20).

Feedback do Bruno, item 9 da 24ª leva: ele precisa emitir a autodeclaração a
partir da página da pessoa.

O gerador SEMPRE existiu (`fichas.gerar_autodeclaracao_residencia`). O que não
existia era a **porta**: o documento só nascia dentro do wizard, quando o
candidato declara que o comprovante de endereço está no nome de outra pessoa
(`ficha.py::_sincronizar_autodeclaracao_residencia`). Se ele não declarou — ou se
o caso apareceu depois, que é o normal — o RH não tinha como emitir.

É o padrão da v3.16: **ação que só existe dentro de outra ação não tem porta**.
Lá era o requerimento do creche, preso dentro de um `except`; aqui é a
autodeclaração, presa dentro do salvamento do endereço.

O que este teste trava:

1. **A porta existe e funciona.** Um clique na ficha cria a `Assinatura`, e ela
   segue o fluxo normal (aparece para assinar, entra no dossiê, conta como
   pendência).
2. **Motivo é obrigatório.** O documento é uma EXCEÇÃO — emiti-lo fora do fluxo
   em que o candidato declara o titular é decisão do RH, e daqui a seis meses o
   registro precisa dizer por quê (mesmo desenho do `documento-especifico` e do
   `reverter` da v1.65).
3. **Não duplica assinatura viva**, e o 409 diz se está pendente ou ASSINADA —
   reemitir apagaria o que a pessoa assinou, e a tela precisa distinguir os dois
   casos para orientar quem opera.
4. **A listagem diz que a pessoa já tem**, para a tela não oferecer o que vai
   levar 409.
5. **O ato vai para a auditoria** com o motivo.

Mutações que este teste precisa reprovar:

  1. aceitar motivo vazio -> bloco 2
  2. não conferir assinatura viva (deixar duplicar) -> bloco 3
  3. `tem_autodeclaracao` sempre False -> bloco 4

Precisa dos containers de teste (Postgres em 55432, MinIO em 59000).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_autodeclaracao_ficha.py
"""

import os
import uuid

for _chave, _valor in dict(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@exemplo.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
).items():
    os.environ.setdefault(_chave, _valor)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.assinatura import Assinatura, DocumentoAssinavel  # noqa: E402
from app.models.candidato import Candidato, StatusCandidato  # noqa: E402

c = TestClient(app, raise_server_exceptions=False)

EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA. {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]
falhas: list[str] = []
DOC = DocumentoAssinavel.autodeclaracao_residencia


def checar(cond, msg):
    if cond:
        print(f"  ok      {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


# Dados fictícios — o repositório é PÚBLICO.
db = SessionLocal()
try:
    cand = Candidato(nome_completo=f"Candidato Autodecl {SUF}",
                     email=f"autodecl.{SUF}@exemplo.com.br",
                     cargo_funcao="Auxiliar de Teste",
                     status=StatusCandidato.convidado, origem="admissao")
    db.add(cand)
    db.commit()
    db.refresh(cand)
    CID = str(cand.id)
finally:
    db.close()

print("\n1. a porta existe: um clique na ficha cria o documento")
r = c.post(f"/api/rh/candidatos/{CID}/autodeclaracao-residencia",
           headers=RH, json={"motivo": "comprovante no nome do pai"})
checar(r.status_code == 200, f"emitir responde 200 (veio {r.status_code}) — {r.text[:120]}")

# A prova é o ESTADO do banco, não o código da resposta: uma rota que responde
# 200 sem criar nada passaria numa asserção de status.
db = SessionLocal()
try:
    a = db.scalar(select(Assinatura).where(Assinatura.candidato_id == uuid.UUID(CID),
                                           Assinatura.documento == DOC,
                                           Assinatura.invalidada_em.is_(None)))
    checar(a is not None, "a Assinatura foi criada no banco")
    checar(a is not None and a.aguardando_liberacao is False,
           "nasce LIBERADA — aparece para a pessoa assinar, sem depender de disparo")
    checar(a is not None and a.assinado_em is None,
           "nasce pendente, não assinada")
finally:
    db.close()

print("\n2. motivo é obrigatório")
db = SessionLocal()
try:
    outro = Candidato(nome_completo=f"Sem Motivo {SUF}",
                      email=f"semmotivo.{SUF}@exemplo.com.br",
                      cargo_funcao="Auxiliar de Teste",
                      status=StatusCandidato.convidado, origem="admissao")
    db.add(outro)
    db.commit()
    db.refresh(outro)
    CID2 = str(outro.id)
finally:
    db.close()

for corpo, rotulo in [({"motivo": ""}, "vazio"), ({"motivo": "   "}, "só espaços")]:
    r = c.post(f"/api/rh/candidatos/{CID2}/autodeclaracao-residencia",
               headers=RH, json=corpo)
    checar(r.status_code == 422,
           f"motivo {rotulo} é recusado com 422 (veio {r.status_code})")

# E a recusa não pode ter criado nada pelo caminho.
db = SessionLocal()
try:
    n = db.scalars(select(Assinatura).where(
        Assinatura.candidato_id == uuid.UUID(CID2))).all()
    checar(len(n) == 0, f"a recusa não criou documento nenhum (achou {len(n)})")
finally:
    db.close()

print("\n3. não duplica assinatura viva, e diz em que estado está")
r = c.post(f"/api/rh/candidatos/{CID}/autodeclaracao-residencia",
           headers=RH, json={"motivo": "de novo"})
checar(r.status_code == 409, f"a segunda emissão responde 409 (veio {r.status_code})")
if r.status_code == 409:
    d = r.json().get("detail") or {}
    checar(d.get("erro") == "documento_ja_existe", f"o erro é nomeado — veio {d}")
    checar(d.get("assinado") is False,
           "e diz que está PENDENTE, não assinada — reemitir apagaria o assinado, "
           f"então a tela precisa distinguir (veio {d.get('assinado')!r})")

db = SessionLocal()
try:
    vivas = db.scalars(select(Assinatura).where(
        Assinatura.candidato_id == uuid.UUID(CID),
        Assinatura.documento == DOC,
        Assinatura.invalidada_em.is_(None))).all()
    checar(len(vivas) == 1, f"continua existindo UMA só (achou {len(vivas)})")
finally:
    db.close()

print("\n4. a listagem da ficha diz que a pessoa já tem")
r = c.get(f"/api/rh/candidatos/{CID}/documentos-especificos", headers=RH)
checar(r.status_code == 200, f"listagem responde 200 (veio {r.status_code})")
if r.status_code == 200:
    checar(r.json().get("tem_autodeclaracao") is True,
           "quem JÁ tem é marcado — senão a tela oferece de novo e o RH leva um "
           "409 que o sistema podia ter evitado")

r = c.get(f"/api/rh/candidatos/{CID2}/documentos-especificos", headers=RH)
if r.status_code == 200:
    checar(r.json().get("tem_autodeclaracao") is False,
           "quem NÃO tem continua podendo emitir")

print("\n5. o ato vai para a auditoria, com o motivo")
db = SessionLocal()
try:
    from app.models.evento import EventoAuditoria
    ev = db.scalars(select(EventoAuditoria).where(
        EventoAuditoria.candidato_id == uuid.UUID(CID),
        EventoAuditoria.acao == "autodeclaracao_residencia_emitida")).all()
    checar(len(ev) >= 1, f"o evento foi registrado (achou {len(ev)})")
    checar(any((e.detalhe or {}).get("motivo") == "comprovante no nome do pai"
               for e in ev),
           "o motivo escrito pelo RH está na auditoria — é o que explica, depois, "
           "por que esta pessoa recebeu o documento")
finally:
    db.close()

print("\n6. candidato inexistente responde 404")
r = c.post(f"/api/rh/candidatos/{uuid.uuid4()}/autodeclaracao-residencia",
           headers=RH, json={"motivo": "x"})
checar(r.status_code == 404, f"404 para quem não existe (veio {r.status_code})")

# Limpeza: o banco de teste é reaproveitado, então o que este teste cria sai no
# fim. ⚠️ A AUDITORIA tem FK para `candidato` e precisa sair ANTES — apagar o
# candidato direto estoura `ForeignKeyViolation`. (Em produção nada disso é
# apagado: a trilha é o registro de que o ato existiu.)
db = SessionLocal()
try:
    from app.models.evento import EventoAuditoria
    # ⚠️ DOIS commits: no mesmo, o SQLAlchemy ordena os DELETEs por tabela e o
    # do candidato pode sair antes do da auditoria — que tem FK para ele. O
    # sintoma é `ForeignKeyViolation` numa limpeza que "está na ordem certa" no
    # código. Filhos primeiro, commit, depois o pai.
    for cid in (CID, CID2):
        for ev in db.scalars(select(EventoAuditoria).where(
                EventoAuditoria.candidato_id == uuid.UUID(cid))).all():
            db.delete(ev)
        for a in db.scalars(select(Assinatura).where(
                Assinatura.candidato_id == uuid.UUID(cid))).all():
            db.delete(a)
    db.commit()
    for cid in (CID, CID2):
        obj = db.get(Candidato, uuid.UUID(cid))
        if obj is not None:
            db.delete(obj)
    db.commit()
finally:
    db.close()

print()
if falhas:
    print(f"test_autodeclaracao_ficha: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_autodeclaracao_ficha: OK")
