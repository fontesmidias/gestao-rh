"""Exigências: padrão de fábrica → padrão da casa → exceção da pessoa (v2.80).

Pedido do Bruno (2026-08-07): *"ter a opção de, no front, por padrão vir marcado
os campos obrigatórios para todos (lógico, aqueles que têm que ser
obrigatórios), mas customizável por candidato, pelo pessoal do RH. Daí ter um
padrão geral lá em configurações"*.

Antes disto a obrigatoriedade era CHUMBADA em dois lugares — `services/slots.py`
(documentos) e `api/ficha.py` (campos). Mudar qualquer coisa exigia deploy, e o
caso excepcional (a pessoa que comprovadamente não tem aquele documento) não
tinha saída nenhuma.

O que este teste trava:

1. **A herança em três camadas**, com a mais específica vencendo e a ausência
   HERDANDO — nunca virando "não é obrigatório". `None` é silêncio; `False` é
   uma DECISÃO de dispensar, e o sistema precisa distinguir os dois.
2. **`SEMPRE_OBRIGATORIOS` não se desmarca.** Não é preciosismo: sem
   `aceite_lgpd` não há base legal para guardar a ficha; sem `pessoais.email` o
   código de assinatura não chega e a admissão para no meio; sem
   `documentos.cpf` a pessoa não casa em creche, Tirvu nem ponto. Desmarcá-los
   quebraria o fluxo LONGE daqui, onde ninguém ligaria uma coisa à outra.
3. **O efeito é REAL**, não decorativo: dispensar tira a pendência de verdade e
   ressincroniza o slot na hora. Um teste que só conferisse a resposta da rota
   passaria com o sistema continuando a exigir o documento.
4. **A dispensa SOBREVIVE ao autosave.** É o ponto mais importante: a
   `sincronizar_slots` reescreve `slot.obrigatorio` a cada execução, e o wizard
   salva a cada 900ms. Se a decisão morasse no slot, sumiria sozinha em
   segundos — por isso ela mora em `Candidato.exigencias`.
5. **Desfazer devolve ao padrão**, sem o RH precisar saber de cor qual era.

Mutações verificadas:
  1. exceção da pessoa não vence o padrão      -> bloco 3 falha
  2. `SEMPRE_OBRIGATORIOS` deixa de travar     -> bloco 5 falha
  3. `pendencias_da_ficha` não filtra          -> bloco 4 falha
  4. `slots.py` ignora o mapa de exigências    -> bloco 6 falha
  5. motivo deixa de ser obrigatório           -> bloco 3 falha

Precisa dos containers de teste.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_exigencias.py
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

from app.api.ficha import pendencias_da_ficha  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402
from app.models.documento import SlotDocumento, TipoDocumento  # noqa: E402
from app.services.slots import sincronizar_slots  # noqa: E402

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


def novo_candidato():
    with SessionLocal() as db:
        cand = Candidato(nome_completo=f"Exigencias {SUF}-{uuid.uuid4().hex[:4]}",
                         email=f"exig-{uuid.uuid4().hex[:8]}@exemplo.com",
                         cargo_funcao="Vigia")
        db.add(cand)
        db.commit()
        return str(cand.id)


def por_chave(lista):
    return {x["chave"]: x for x in lista}


def limpar_padrao_da_casa():
    """Devolve a config global ao padrão de fábrica.

    O teste MEXE numa configuração compartilhada — deixá-la suja mudaria o
    comportamento de toda a base e faria a execução seguinte medir outra coisa
    (a lição do teste destrutivo da v2.66).
    """
    for grupo, chave in (("documentos", "diplomas"), ("campos", "pessoais.cor_raca")):
        c.put("/api/rh/config/exigencias", headers=RH,
              json={"grupo": grupo, "chave": chave, "obrigatorio": None})


limpar_padrao_da_casa()
cid = novo_candidato()

# --------------------------------------------------------------------------
print("\n1. o padrão de FÁBRICA espelha o que estava chumbado")
# --------------------------------------------------------------------------
r = c.get(f"/api/rh/candidatos/{cid}/exigencias", headers=RH)
checar(r.status_code == 200, f"GET responde 200 ({r.status_code})")
docs = por_chave(r.json()["documentos"])
campos = por_chave(r.json()["campos"])

checar(docs["rg"]["obrigatorio"] is True and docs["rg"]["origem"] == "fabrica",
       "RG nasce obrigatório, vindo da fábrica")
checar(docs["diplomas"]["obrigatorio"] is False,
       "diplomas nasce OPCIONAL (decisão do RH de 2026-07-15, preservada)")
checar(docs["comp_escolaridade"]["obrigatorio"] is False,
       "comprovante de escolaridade continua opcional")
checar(campos["pessoais.cor_raca"]["obrigatorio"] is True,
       "campo de cor/raça nasce obrigatório")
checar(all("rotulo" in d and d["rotulo"] != d["chave"] for d in list(docs.values())[:5]),
       "todo item tem rótulo LEGÍVEL — o RH não deve ver `trabalho_banco.pix_tipo`")

# --------------------------------------------------------------------------
print("\n2. o padrão da CASA vale para todos")
# --------------------------------------------------------------------------
r = c.put("/api/rh/config/exigencias", headers=RH,
          json={"grupo": "documentos", "chave": "diplomas", "obrigatorio": True})
checar(r.status_code == 200, f"PUT do padrão responde 200 ({r.status_code})")

outro = novo_candidato()
d2 = por_chave(c.get(f"/api/rh/candidatos/{outro}/exigencias", headers=RH).json()["documentos"])
checar(d2["diplomas"]["obrigatorio"] is True,
       "candidato NOVO já nasce com o padrão da casa")
checar(d2["diplomas"]["origem"] == "casa",
       "e a tela sabe que veio da CASA, não da fábrica — é isso que deixa "
       "dizer 'alguém configurou' em vez de só mostrar um check")

# --------------------------------------------------------------------------
print("\n3. a exceção da PESSOA vence o padrão")
# --------------------------------------------------------------------------
# ⚠️ Mutações 1 e 5.
r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
          json={"grupo": "documentos", "chave": "diplomas", "obrigatorio": False,
                "motivo": "Cargo operacional, não exige diploma"})
checar(r.status_code == 200, f"dispensar para UMA pessoa responde 200 ({r.status_code})")

d3 = por_chave(c.get(f"/api/rh/candidatos/{cid}/exigencias", headers=RH).json()["documentos"])
checar(d3["diplomas"]["obrigatorio"] is False,
       "a exceção da pessoa VENCE o padrão da casa")
checar(d3["diplomas"]["origem"] == "pessoa", "e a origem diz que foi decidida aqui")

d4 = por_chave(c.get(f"/api/rh/candidatos/{outro}/exigencias", headers=RH).json()["documentos"])
checar(d4["diplomas"]["obrigatorio"] is True,
       "a OUTRA pessoa continua com o padrão — a exceção não vazou")

r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
          json={"grupo": "campos", "chave": "pessoais.escolaridade", "obrigatorio": False})
checar(r.status_code == 422,
       "sem MOTIVO é recusado — é ele que explica meses depois por que esta "
       "pessoa não entregou o que todo mundo entrega")

# --------------------------------------------------------------------------
print("\n4. o efeito é REAL nas pendências de CAMPO")
# --------------------------------------------------------------------------
# ⚠️ Mutação 3: `pendencias_da_ficha` sem o filtro -> estas asserções falham.
#
# Sem isto o teste passaria com a rota respondendo bonito e o sistema
# continuando a exigir o campo — decoração, não funcionalidade.
with SessionLocal() as db:
    cand = db.get(Candidato, uuid.UUID(cid))
    antes = pendencias_da_ficha(db, cand)
checar("pessoais.cor_raca" in antes, "cor/raça é pendência antes de dispensar")

c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
      json={"grupo": "campos", "chave": "pessoais.cor_raca", "obrigatorio": False,
            "motivo": "não quis declarar"})
with SessionLocal() as db:
    cand = db.get(Candidato, uuid.UUID(cid))
    depois = pendencias_da_ficha(db, cand)
checar("pessoais.cor_raca" not in depois, "e DEIXA de ser depois")
checar(len(depois) == len(antes) - 1,
       f"exatamente UMA pendência a menos — dispensar um campo não pode "
       f"derrubar outros ({len(antes)} -> {len(depois)})")

# --------------------------------------------------------------------------
print("\n5. o que é do SISTEMA não se desmarca")
# --------------------------------------------------------------------------
# ⚠️ Mutação 2: tirar o guard de `SEMPRE_OBRIGATORIOS` -> estas falham.
#
# Sem e-mail o código de assinatura não chega; sem CPF a pessoa não casa em
# creche/Tirvu/ponto; sem aceite LGPD não há base legal. Quebraria LONGE daqui.
# ⚠️ Afirma sobre o MOTIVO da recusa, não só sobre o 422 (lição achada por
# mutação): estas chaves também não estão no `CAMPOS_PADRAO`, então mesmo SEM o
# guard elas cairiam em `chave_desconhecida` — 422 igual. Conferir só o código
# faria o teste passar com a proteção removida, e o defeito apareceria no dia em
# que alguém acrescentasse a chave ao catálogo. É a família da tautologia da
# v2.64: a asserção precisa distinguir POR QUE foi recusado.
for grupo, chave in (("campos", "pessoais.email"), ("campos", "documentos.cpf")):
    r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
              json={"grupo": grupo, "chave": chave, "obrigatorio": False,
                    "motivo": "tentativa"})
    checar(r.status_code == 422 and r.json().get("detail") == "exigencia_do_sistema",
           f"`{chave}` é recusado por ser DO SISTEMA, não por chave desconhecida "
           f"(veio {r.status_code} {r.json().get('detail')!r})")
    r = c.put("/api/rh/config/exigencias", headers=RH,
              json={"grupo": grupo, "chave": chave, "obrigatorio": False})
    checar(r.status_code == 422 and r.json().get("detail") == "exigencia_do_sistema",
           f"`{chave}` idem no padrão da casa (veio {r.json().get('detail')!r})")

with SessionLocal() as db:
    cand = db.get(Candidato, uuid.UUID(cid))
    pend = pendencias_da_ficha(db, cand)
checar("pessoais.email" in pend or cand.email,
       "e-mail continua sendo cobrado (ou já está preenchido)")

r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
          json={"grupo": "documentos", "chave": "coisa_inexistente",
                "obrigatorio": False, "motivo": "x"})
checar(r.status_code == 422, "chave fora do catálogo é recusada")
r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
          json={"grupo": "outro_grupo", "chave": "rg", "obrigatorio": False, "motivo": "x"})
checar(r.status_code == 422, "grupo inválido é recusado")

# --------------------------------------------------------------------------
print("\n6. a dispensa SOBREVIVE ao autosave (o ponto do desenho)")
# --------------------------------------------------------------------------
# ⚠️ Mutação 4: `slots.py` ignorando o mapa -> estas asserções falham.
#
# A `sincronizar_slots` REESCREVE `slot.obrigatorio` a cada execução, e o
# wizard salva a cada 900ms. Se a decisão morasse no slot, ela sumiria sozinha
# em segundos — este bloco é o que prova que ela mora no lugar certo.
c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
      json={"grupo": "documentos", "chave": "rg", "obrigatorio": False,
            "motivo": "Perdeu o RG; apresentou CNH"})

with SessionLocal() as db:
    cand = db.get(Candidato, uuid.UUID(cid))
    slot = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == cand.id,
        SlotDocumento.tipo == TipoDocumento.rg))
    checar(slot is not None and slot.obrigatorio is False,
           "o slot do RG passou a NÃO obrigatório")

    # Simula o autosave do wizard, várias vezes.
    for _ in range(3):
        sincronizar_slots(db, cand)
    db.commit()
    slot = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == cand.id,
        SlotDocumento.tipo == TipoDocumento.rg))
    checar(slot is not None and slot.obrigatorio is False,
           "e CONTINUA não obrigatório depois de 3 sincronizações — a decisão "
           "não mora no slot, que é reescrito a cada autosave")

# --------------------------------------------------------------------------
print("\n7. desfazer devolve ao padrão")
# --------------------------------------------------------------------------
r = c.put(f"/api/rh/candidatos/{cid}/exigencias", headers=RH,
          json={"grupo": "documentos", "chave": "rg", "obrigatorio": None})
checar(r.status_code == 200, "desfazer responde 200 (e não exige motivo)")
d5 = por_chave(c.get(f"/api/rh/candidatos/{cid}/exigencias", headers=RH).json()["documentos"])
checar(d5["rg"]["obrigatorio"] is True and d5["rg"]["origem"] == "fabrica",
       "o RG volta ao padrão SEM o RH precisar saber de cor qual era")

with SessionLocal() as db:
    cand = db.get(Candidato, uuid.UUID(cid))
    sincronizar_slots(db, cand)
    db.commit()
    slot = db.scalar(select(SlotDocumento).where(
        SlotDocumento.candidato_id == cand.id,
        SlotDocumento.tipo == TipoDocumento.rg))
    checar(slot is not None and slot.obrigatorio is True,
           "e o slot volta a ser obrigatório")

# --------------------------------------------------------------------------
print("\n8. a rota é do RH")
# --------------------------------------------------------------------------
checar(c.get(f"/api/rh/candidatos/{cid}/exigencias").status_code in (401, 403),
       "GET sem token é recusado")
checar(c.put(f"/api/rh/candidatos/{cid}/exigencias",
             json={"grupo": "documentos", "chave": "rg"}).status_code in (401, 403),
       "PUT sem token é recusado")
checar(c.get(f"/api/rh/candidatos/{uuid.uuid4()}/exigencias",
             headers=RH).status_code == 404, "candidato inexistente dá 404")

# Devolve a config compartilhada ao estado de fábrica.
limpar_padrao_da_casa()

print()
if falhas:
    print(f"test_exigencias: {len(falhas)} FALHA(S)")
    for f_ in falhas:
        print(f"  - {f_}")
    raise SystemExit(1)
print("test_exigencias: OK")
