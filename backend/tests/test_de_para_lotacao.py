"""De-para lotação → posto de serviço (v2.40).

Fecha a lacuna medida na v2.39: cargo casa em 100% e jornada em 99%, mas
**posto casa em 11%**. A lotação vem abreviada na planilha do Tirvu ("INEP
ADM", "ANAC") e o apelido do posto aqui é o padrão longo ("ANAC - 14/2026 -
AEROPORTO"). Não é falha de parser: `ANAC` **é** ambíguo — pode ser a sede ou o
aeroporto, e nenhum algoritmo resolve isso honestamente.

O que este teste protege:

1. **A sugestão ordena, nunca decide.** Quando duas opções empatam (o caso
   "ANAC"), as duas sobem juntas — é justamente a ambiguidade que precisa
   chegar aos olhos do RH.
2. **A fila é ordenada por PESSOAS afetadas**, não por ordem alfabética:
   resolver "INEP ADM" (174 pessoas nos dados reais) vale mais que uma lotação
   com 1.
3. **O de-para confirmado passa a valer no vínculo em massa** — se não valesse,
   a decisão do RH seria decoração.
4. **Reconfirmar corrige** em vez de duplicar: de-para errado tem que ter
   conserto sem apagar e recriar.
5. **O que já foi decidido some da fila** — perguntar de novo é desrespeito
   com quem já respondeu.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_de_para_lotacao.py
"""

import io
import os
import pathlib
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
from openpyxl import Workbook  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato, LotacaoTirvu, PostoServico  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

CAB = ["ID", "CPF", "Colaborador", "PCD?", "Deficiência", "Status", "Lotação",
       "Cargo", "Jornada de Trabalho"]


def planilha(linhas):
    wb = Workbook()
    ws = wb.active
    ws.append(CAB)
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def cpf_novo(n: int) -> str:
    return f"7{(uuid.uuid4().int + n) % 10**10:010d}"


# ----------------------------------------------------------------- arranjo
# Reproduz o caso real: uma sigla que serve a DOIS postos (ANAC sede x
# aeroporto) e uma lotação com muita gente (INEP ADM).
suf = uuid.uuid4().hex[:6].upper()
SIGLA = f"ANAC{suf}"
INEP = f"INEP{suf} ADM"
with SessionLocal() as db:
    sede = PostoServico(nome=f"{SIGLA} - 14/2026 - SEDE")
    aero = PostoServico(nome=f"{SIGLA} - 14/2026 - AEROPORTO")
    inep = PostoServico(nome=f"INEP{suf} - 07/2023 - ADMINISTRATIVO")
    db.add_all([sede, aero, inep])
    db.flush()
    ids = {"sede": str(sede.id), "aero": str(aero.id), "inep": str(inep.id)}
    # 3 pessoas em INEP ADM e 1 na sigla ambígua
    cpfs = [cpf_novo(i) for i in range(4)]
    for i, cpf in enumerate(cpfs):
        db.add(Candidato(nome_completo=f"Pessoa {i} {suf}", cpf=cpf, situacao="ativo",
                         email=f"p{i}{suf}@ex.com"))
    db.commit()

xlsx = planilha([
    [str(i), cpfs[i], f"Pessoa {i} {suf}", "NÃO", "", "ATIVO",
     INEP if i < 3 else SIGLA, "AUXILIAR", ""]
    for i in range(4)
])

# ======================================= 1. a fila e a ordem das sugestões
print("\n[a fila do que falta decidir]")
r = c.post("/api/rh/postos/de-para/preview", headers=H,
           files={"arquivo": ("c.xlsx", xlsx, "application/vnd.ms-excel")})
checar(r.status_code == 200, f"preview aceito ({r.status_code}) {r.text[:150]}")
prev = r.json()
nossas = [p for p in prev["pendentes"] if p["lotacao"] in (INEP, SIGLA)]
checar(len(nossas) == 2, f"as duas lotações sem posto aparecem ({len(nossas)})")

pos_inep = next(i for i, p in enumerate(prev["pendentes"]) if p["lotacao"] == INEP)
pos_sigla = next(i for i, p in enumerate(prev["pendentes"]) if p["lotacao"] == SIGLA)
checar(pos_inep < pos_sigla,
       "quem tem MAIS gente esperando vem primeiro (3 antes de 1) — resolver a "
       "fila na ordem alfabética desperdiça o tempo do RH")

amb = next(p for p in prev["pendentes"] if p["lotacao"] == SIGLA)
nomes = [s["posto_nome"] for s in amb["sugestoes"]]
checar(any("SEDE" in n for n in nomes) and any("AEROPORTO" in n for n in nomes),
       "a sigla ambígua sobe as DUAS possibilidades — é a ambiguidade que "
       "precisa chegar ao RH, não ser desempatada no escuro")
checar(len(amb["sugestoes"]) >= 2 and abs(amb["sugestoes"][0]["score"]
                                          - amb["sugestoes"][1]["score"]) < 0.15,
       "e elas ficam com pontuação parecida, que é o sinal para a tela NÃO "
       "pré-selecionar nenhuma")

so_inep = next(p for p in prev["pendentes"] if p["lotacao"] == INEP)
checar(so_inep["pessoas"] == 3, f"a fila diz quantas pessoas dependem ({so_inep['pessoas']})")
checar(so_inep["sugestoes"] and "ADMINISTRATIVO" in so_inep["sugestoes"][0]["posto_nome"],
       "o posto certo é a primeira sugestão quando não há ambiguidade")

with SessionLocal() as db:
    checar(db.scalar(select(LotacaoTirvu).where(
        LotacaoTirvu.lotacao_rotulo == INEP)) is None,
        "o preview NÃO gravou nada")

# --------- o caso real que quase passou: semelhança de letras engana
# Nos dados de produção, "INEP ADM" (174 pessoas) pontuava 0.67 com "IPAM" —
# as letras I-P-A-M estão todas lá, na ordem — e só 0.47 com o posto certo.
# Um RH apressado aceitaria a sugestão e mandaria 174 pessoas para o contrato
# errado. A PALAVRA inteira é o sinal que desempata.
print("\n[semelhança de letras não pode ganhar de palavra inteira]")
with SessionLocal() as db:
    isca = PostoServico(nome=f"IPAM{suf}")
    db.add(isca)
    db.commit()
    r = c.post("/api/rh/postos/de-para/preview", headers=H,
               files={"arquivo": ("c.xlsx", planilha([
                   [str(i), cpfs[i], f"Pessoa {i} {suf}", "NÃO", "", "ATIVO",
                    INEP, "AUXILIAR", ""] for i in range(3)]),
                   "application/vnd.ms-excel")})
    item = next(p for p in r.json()["pendentes"] if p["lotacao"] == INEP)
    primeiro = item["sugestoes"][0]["posto_nome"] if item["sugestoes"] else ""
    checar("ADMINISTRATIVO" in primeiro,
           f"o posto que compartilha a PALAVRA 'INEP{suf}' vem na frente do "
           f"anagrama 'IPAM{suf}' (veio: {primeiro!r})")

# ====================================== 2. confirmar, e o efeito no vínculo
print("\n[a decisão do RH passa a valer]")
r = c.post("/api/rh/postos/de-para/confirmar", headers=H, json={"itens": [
    {"lotacao": INEP, "posto_id": ids["inep"]},
    {"lotacao": SIGLA, "posto_id": ids["aero"]}]})
checar(r.status_code == 200 and r.json()["criados"] == 2, f"de-para gravado ({r.text})")

r = c.post("/api/rh/colaboradores/vinculos/preview", headers=H,
           files={"arquivo": ("c.xlsx", xlsx, "application/vnd.ms-excel")})
prev2 = r.json()
nossos = [i for i in prev2["itens"] if i["cpf"] in cpfs]
checar(len(nossos) == 4, f"as 4 pessoas entram como prontas ({len(nossos)})")
checar(all(i["posto"]["situacao"] == "preencher" and i["posto"]["id"] for i in nossos),
       "o posto agora casa por causa do de-para — sem isso, a decisão do RH "
       "seria decoração")
do_ambiguo = next(i for i in nossos if i["cpf"] == cpfs[3])
checar(do_ambiguo["posto"]["id"] == ids["aero"],
       "e casa com o posto que o RH escolheu, não com o outro parecido")

r = c.post("/api/rh/colaboradores/vinculos/aplicar", headers=H, json={"itens": [
    {"cpf": i["cpf"], "posto_id": i["posto"]["id"]} for i in nossos]})
checar(r.status_code == 200 and r.json()["posto"] == 4, f"4 postos gravados ({r.text})")
with SessionLocal() as db:
    p = db.scalar(select(Candidato).where(Candidato.cpf == cpfs[3]))
    checar(str(p.posto_servico_id) == ids["aero"], "a pessoa ficou no posto escolhido")

# ================================== 3. já decidido some da fila; reconfirmar corrige
print("\n[não perguntar duas vezes, e poder corrigir]")
r = c.post("/api/rh/postos/de-para/preview", headers=H,
           files={"arquivo": ("c.xlsx", xlsx, "application/vnd.ms-excel")})
pendentes = [p["lotacao"] for p in r.json()["pendentes"]]
checar(INEP not in pendentes and SIGLA not in pendentes,
       "o que já foi decidido não volta a perguntar")

r = c.post("/api/rh/postos/de-para/confirmar", headers=H, json={"itens": [
    {"lotacao": SIGLA, "posto_id": ids["sede"]}]})
checar(r.status_code == 200 and r.json()["atualizados"] == 1,
       f"reconfirmar CORRIGE o destino em vez de duplicar ({r.text})")
with SessionLocal() as db:
    todos = db.scalars(select(LotacaoTirvu).where(
        LotacaoTirvu.lotacao_rotulo == SIGLA)).all()
    checar(len(todos) == 1 and str(todos[0].posto_servico_id) == ids["sede"],
           "continua havendo UMA linha para a lotação, apontando para o novo posto")

r = c.post("/api/rh/postos/de-para/confirmar", headers=H, json={"itens": [
    {"lotacao": "QUALQUER", "posto_id": str(uuid.uuid4())}]})
checar(r.status_code == 422, f"posto inexistente é recusado ({r.status_code})")

# ============================ 4. a planilha real: o tamanho da fila de verdade
DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "modelos de arquivos exportados do tirvu"
real = next(iter(sorted(DOCS.glob("Colaboradores*.xlsx"))), None)
if real:
    print(f"\n[planilha real: {real.name}]")
    r = c.post("/api/rh/postos/de-para/preview", headers=H,
               files={"arquivo": (real.name, real.read_bytes(), "application/vnd.ms-excel")})
    p = r.json()
    print(f"       {len(p['pendentes'])} lotações a decidir · "
          f"{p['total_pessoas']} pessoas esperando")
    checar(len(p["pendentes"]) > 0, "a fila real tem itens")
    ordem = [x["pessoas"] for x in p["pendentes"]]
    checar(ordem == sorted(ordem, reverse=True),
           f"a fila real vem da que mais afeta gente para a que menos afeta: {ordem[:5]}")
    com_sugestao = [x for x in p["pendentes"] if x["sugestoes"]]
    print(f"       {len(com_sugestao)} têm ao menos uma sugestão")

print()
if FALHAS:
    print(f"test_de_para_lotacao: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_de_para_lotacao: OK")
