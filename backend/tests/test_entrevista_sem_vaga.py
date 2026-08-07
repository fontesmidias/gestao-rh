"""Entrevista sem vaga cadastrada, cadastro da pessoa na hora e currículo pelo RH.

Os três pedidos do Bruno de 2026-08-07, com os prints do formulário de nova
entrevista (v2.74):

1. *"pode ser que a pessoa não esteja no banco, logo, tem que permitir cadastrar
   a pessoa ali na hora, em regra o RH pode cadastrar com nome e whatsapp, para
   depois preencher mais informações"* — mais, depois: *"você esqueceu da opção
   de poder anexar currículo"*.
2. *"ali na 'a pessoa é', pode ter a opção outros e o RH já preenche e vê os que
   ele já cadastrou"*.
3. *"na vaga, podem ser dois campos, cargo e posto, puxando todos já cadastrados
   ou tendo a opção de criar ali mesmo"*.

O que este teste trava, e por quê:

**O currículo do RH tinha uma rota que não existia.** A v2.73 escreveu na tela
"o currículo pode ser anexado depois, pela ficha da pessoa" — e não havia como:
a única rota de upload era a PÚBLICA, autorizada por um `upload_token` com TTL
de 30 min emitido no cadastro público. O RH não tem token nenhum. Promessa na
interface sem rota atrás é a mesma família do "documento que não nasce" (v2.69):
ninguém vê o que está faltando, porque a tela não acusa nada.

**Cargo e posto são ALTERNATIVA à vaga, não substituto.** Havendo vaga, ela
manda — três campos dizendo a mesma coisa fariam o RH preencher dois por engano
(regra do "um assunto, um controle", v2.30). E o `posto_nome` é SNAPSHOT pela
mesma razão do `vaga_titulo`: o posto vai para a lixeira e a entrevista tem que
continuar dizendo para ONDE a conversa foi.

Mutações verificadas:
  1. `cargo`/`posto_id` não são gravados                  -> bloco 2 falha
  2. `posto_nome` deixa de ser snapshot (lê do posto vivo) -> bloco 3 falha
  3. cargo da VAGA perde precedência sobre o digitado      -> bloco 4 falha
  4. a troca de currículo não remove o arquivo anterior    -> bloco 6 falha
  5. `POST /rh/talentos/{id}/curriculo` sem `requer_rh`    -> bloco 5 falha

Precisa dos containers de teste (banco + MinIO).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_entrevista_sem_vaga.py
"""

import os
import uuid

for _chave, _valor in dict(
    DATABASE_URL="postgresql+psycopg://admissao:admissao@localhost:55432/admissao",
    MINIO_ENDPOINT="localhost:59000",
    MINIO_ACCESS_KEY="minio",
    MINIO_SECRET_KEY="minio12345",
    MINIO_SECURE="false",
    RH_ADMIN_EMAIL="rh@greenhousedf.com.br",
    RH_ADMIN_PASSWORD="senha-teste-123",
    SECRET_KEY="segredo-de-teste",
    BASE_URL="http://localhost:8090",
).items():
    os.environ.setdefault(_chave, _valor)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entrevista import Entrevista  # noqa: E402
from app.models.talento import Talento  # noqa: E402
from app.services import storage  # noqa: E402

c = TestClient(app)

EMAIL = os.environ["RH_ADMIN_EMAIL"]
SENHA = os.environ["RH_ADMIN_PASSWORD"]
r = c.post("/api/rh/auth/login", json={"email": EMAIL, "senha": SENHA})
assert r.status_code == 200, (
    f"login falhou ({r.status_code}): confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD "
    f"— `criar_admin_inicial` só cria o admin com a tabela VAZIA. {r.text}")
RH = {"Authorization": f"Bearer {r.json()['token']}"}

SUF = uuid.uuid4().hex[:8]
falhas: list[str] = []


def checar(cond, msg):
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FALHOU  {msg}")
        falhas.append(msg)


def novo_talento(nome=None, **extra):
    r = c.post("/api/rh/talentos", headers=RH,
               json={"nome": nome or f"Pessoa {SUF}-{uuid.uuid4().hex[:4]}",
                     "forcar": True, **extra})
    assert r.status_code == 201, f"criar talento: {r.status_code} {r.text}"
    return r.json()["id"]


def novo_posto(nome):
    r = c.post("/api/rh/postos", headers=RH,
               json={"nome": nome, "sigla": f"S{uuid.uuid4().hex[:6]}"})
    assert r.status_code in (200, 201), f"criar posto: {r.status_code} {r.text}"
    return r.json().get("id") or r.json().get("posto", {}).get("id")


# --------------------------------------------------------------------------
print("\n1. a pessoa cadastrada NA HORA entra com o mínimo (nome + WhatsApp)")
# --------------------------------------------------------------------------
# É a mesma rota do cadastro à mão (v2.73), então herda tudo: nome padronizado,
# consentimento NÃO fingido e autor registrado. Aqui só se prova que o mínimo
# basta — exigir e-mail ou cargo mataria o caso de uso (pessoa na porta).
r = c.post("/api/rh/talentos", headers=RH,
           json={"nome": f"joão da porta {SUF}", "telefone": "61933332222",
                 "origem": "Cadastrado na entrevista", "forcar": True})
checar(r.status_code == 201, f"nome + telefone bastam ({r.status_code})")
pessoa = r.json()
checar(pessoa["nome"].startswith("João da Porta"),
       f"o nome é padronizado ({pessoa['nome']!r})")
checar(pessoa.get("consentimento_lgpd_em") is None,
       "sem consentimento fingido — a pessoa não estava na tela para aceitar")
checar(bool(pessoa.get("cadastrado_por_nome")), "e fica registrado quem cadastrou")

# --------------------------------------------------------------------------
print("\n2. entrevista SEM vaga grava cargo e posto")
# --------------------------------------------------------------------------
# ⚠️ Mutação 1: não gravar `cargo`/`posto_id` -> estas asserções falham.
POSTO = f"INEP - {SUF} - PORTARIA"
pid = novo_posto(POSTO)
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": pessoa["id"], "tipo": "entrevista",
    "cargo": "Recepcionista", "posto_id": pid})
checar(r.status_code == 201, f"cria sem vaga nenhuma ({r.status_code} {r.text[:80]})")
e = r.json()
checar(e.get("vaga_titulo") is None, "não inventa uma vaga")
checar(e.get("cargo") == "Recepcionista", f"o cargo é gravado ({e.get('cargo')!r})")
checar(e.get("posto_nome") == POSTO, f"o posto é gravado ({e.get('posto_nome')!r})")

r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": pessoa["id"], "tipo": "triagem", "posto_id": str(uuid.uuid4())})
checar(r.status_code == 404, "posto inexistente é recusado com 404, não gravado calado")

# --------------------------------------------------------------------------
print("\n3. `posto_nome` é SNAPSHOT — sobrevive ao posto ir para a lixeira")
# --------------------------------------------------------------------------
# ⚠️ Mutação 2: ler o nome do posto VIVO em vez do snapshot -> falha aqui.
#
# Mesma razão do `vaga_titulo` (cenário 4): a entrevista tem que continuar
# legível depois. Dizer para qual posto a conversa foi é metade do registro.
eid = e["id"]

# ⚠️ `DELETE /rh/postos/{id}` é exclusão SOFT (`ativo=False`) — o posto NÃO some
# do banco, justamente para não quebrar quem já aponta para ele. Uma primeira
# versão deste teste esperava a FK virar NULL aí e reprovou CÓDIGO CORRETO: a
# asserção é que estava errada. O delete FÍSICO existe só na ação em massa
# ("excluir definitivo", e só para posto sem vínculo), que é o caminho exercitado
# abaixo — é ele que põe o `ondelete=SET NULL` à prova.
r = c.delete(f"/api/rh/postos/{pid}", headers=RH)
checar(r.status_code in (200, 204), f"desativar o posto responde 2xx ({r.status_code})")
depois = c.get(f"/api/rh/entrevistas/{eid}", headers=RH).json()
checar(depois.get("posto_nome") == POSTO,
       "posto DESATIVADO: a entrevista continua dizendo qual era")

# Agora o delete físico, pela ação em massa. O posto não tem colaborador
# vinculado (foi criado aqui), então "excluir definitivo" o remove de verdade.
r = c.post("/api/rh/postos/massa/acao", headers=RH,
           json={"acao": "excluir", "posto_ids": [pid]})
if r.status_code == 200 and r.json().get("afetados"):
    with SessionLocal() as db:
        reg = db.get(Entrevista, uuid.UUID(eid))
        db.refresh(reg)
        checar(reg is not None and reg.posto_nome == POSTO,
               "posto EXCLUÍDO de vez: o NOME continua na entrevista (snapshot)")
        checar(reg is not None and reg.posto_id is None,
               "e a FK virou NULL (SET NULL) — a linha não quebra")
else:
    # Anuncia em vez de fingir cobertura (o snapshot em si já foi conferido).
    print(f"  (exclusão definitiva não ocorreu: {r.status_code} "
          f"{str(r.json())[:80]} — SET NULL não exercitado nesta execução)")

# --------------------------------------------------------------------------
print("\n4. havendo VAGA, ela manda — cargo e posto não competem com ela")
# --------------------------------------------------------------------------
# ⚠️ Mutação 3: deixar o cargo digitado vencer o da vaga -> falha.
#
# Um assunto, um controle (v2.30): se a vaga existe, é ela que diz para que a
# conversa foi. Deixar os dois valerem faria duas fontes discordarem sobre o
# mesmo fato — e o cargo é o que resolve o ROTEIRO da entrevista.
rv = c.post("/api/rh/vagas", headers=RH, json={
    "titulo": f"Vaga com cargo {SUF}", "descricao": "d", "cargo": "Vigia"})
vid = rv.json()["id"]
r = c.post("/api/rh/entrevistas", headers=RH, json={
    "talento_id": pessoa["id"], "tipo": "entrevista", "vaga_id": vid,
    "cargo": "Office Boy"})
checar(r.status_code == 201, "cria com vaga")
ev = r.json()
checar(ev.get("cargo") == "Vigia",
       f"o cargo vem da VAGA, não do campo digitado ({ev.get('cargo')!r})")
checar(ev.get("vaga_titulo") == f"Vaga com cargo {SUF}", "e a vaga é a snapshot")

# --------------------------------------------------------------------------
print("\n5. o RH anexa currículo pelo painel — a rota que faltava")
# --------------------------------------------------------------------------
# ⚠️ Mutação 5: tirar o `requer_rh` -> a última asserção falha.
#
# A v2.73 escreveu "anexe depois pela ficha" e não havia rota: a única era a
# pública, com `upload_token` de TTL curto que o RH não tem.
tid = novo_talento()
r = c.post(f"/api/rh/talentos/{tid}/curriculo", headers=RH,
           files={"arquivo": ("cv.pdf", b"%PDF-1.4 curriculo", "application/pdf")})
checar(r.status_code == 201, f"POST /rh/talentos/{{id}}/curriculo responde 201 ({r.status_code})")
checar(r.json().get("tem_curriculo") is True, "a resposta já diz que tem currículo")

r = c.post(f"/api/rh/talentos/{tid}/curriculo", headers=RH,
           files={"arquivo": ("virus.exe", b"MZ", "application/octet-stream")})
checar(r.status_code == 422, "formato fora da allowlist é recusado")

r = c.post(f"/api/rh/talentos/{uuid.uuid4()}/curriculo", headers=RH,
           files={"arquivo": ("cv.pdf", b"%PDF", "application/pdf")})
checar(r.status_code == 404, "talento inexistente dá 404")

r = c.post(f"/api/rh/talentos/{tid}/curriculo",
           files={"arquivo": ("cv.pdf", b"%PDF", "application/pdf")})
checar(r.status_code in (401, 403),
       "sem token é recusado — currículo não é rota pública")

# --------------------------------------------------------------------------
print("\n6. trocar o currículo não deixa órfão no storage")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4: não remover o arquivo anterior -> a 2ª asserção falha.
#
# Extensão diferente muda a key, e só o registro aponta para o arquivo: o antigo
# deixaria de ser alcançável por qualquer tela E por qualquer expurgo. É o mesmo
# defeito que o teste do anexo de entrevista pegou na v2.72.
with SessionLocal() as db:
    key_antiga = db.get(Talento, uuid.UUID(tid)).curriculo_key
r = c.post(f"/api/rh/talentos/{tid}/curriculo", headers=RH,
           files={"arquivo": ("cv2.png", b"\x89PNG-novo", "image/png")})
checar(r.status_code == 201, "trocar o currículo é permitido (chega versão nova)")
with SessionLocal() as db:
    key_nova = db.get(Talento, uuid.UUID(tid)).curriculo_key
checar(key_nova != key_antiga, "a key muda quando a extensão muda (.pdf -> .png)")

sumiu = False
try:
    storage.ler(key_antiga)
except Exception:
    sumiu = True
checar(sumiu, "o arquivo ANTERIOR foi removido do storage (não virou órfão)")

r = c.get(f"/api/rh/talentos/{tid}/curriculo", headers=RH)
checar(r.status_code == 200 and r.content == b"\x89PNG-novo",
       "e o download passa a servir o arquivo novo")


print()
if falhas:
    print(f"test_entrevista_sem_vaga: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_entrevista_sem_vaga: OK")
