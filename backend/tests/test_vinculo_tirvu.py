"""Vincular colaboradores em massa a posto, cargo e jornada (v2.39).

Pedido do Bruno em 2026-08-01: *"precisa vincular os colaboradores em massa
também a seus respectivos postos, cargos e jornadas, conforme Tirvu, quero
evitar trabalho manual"*.

A planilha de Colaboradores do Tirvu traz, por pessoa, `Lotação`, `Cargo`,
`Jornada de Trabalho` e `PCD?`. Medido contra os dados reais (1.156 pessoas):
cargo casa em 100%, jornada em 99% e **posto em 11%** — a lotação vem abreviada
("INEP ADM", "ANAC") e o mesmo texto pode ser dois postos diferentes.

O que este teste protege:

1. **Campo vazio é preenchido; campo DIFERENTE não é tocado.** O valor daqui
   pode ser correção feita à mão, e sobrescrever 1.000 registros é
   irreversível na prática. Divergência sai em lista para o RH decidir.
2. **O que não casa aparece com nome e QUANTAS pessoas dependem** — silêncio
   aqui faria o RH achar que vinculou todo mundo.
3. **Nada é gravado no preview** (é a regra da casa: propor, confirmar).
4. **PCD é opcional e rastreado**: é dado de saúde vindo da base do Tirvu, não
   de declaração da pessoa.
5. **Sem N+1**: o número de consultas não acompanha o de linhas da planilha.

Roda com a planilha REAL quando ela existe em `docs/`; sem ela, com uma
amostra embutida de mesmo formato. O teste diz qual fonte usou.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_vinculo_tirvu.py
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
os.environ.setdefault("RH_ADMIN_EMAIL", "rh@exemplo.com.br")
os.environ.setdefault("RH_ADMIN_PASSWORD", "senha-teste-123")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("BASE_URL", "http://localhost:8090")

from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato, Jornada, PostoServico  # noqa: E402
from app.models.ficha import DadosPessoais  # noqa: E402
from app.services import vinculo_tirvu as vt  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@exemplo.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

CABECALHO = ["ID", "CPF", "Colaborador", "PCD?", "Deficiência", "Status", "Lotação",
             "Cargo", "Jornada de Trabalho"]


def planilha(linhas: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(CABECALHO)
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ============================================== 1. classificação (unitária)
print("\n[o que se propõe para cada pessoa]")


class Pessoa:
    def __init__(self, jornada_id=None, cargo=None, posto_id=None, pcd=None):
        self.jornada_id, self.cargo_funcao = jornada_id, cargo
        self.posto_servico_id, self.pcd = posto_id, pcd
        self.nome_completo = "Fulano"


linhas = [CABECALHO,
          ["1", "111.444.777-35", "VAZIO NO PORTAL", "NÃO", "", "ATIVO", "POSTO A", "MOTORISTA", "JORNADA A"],
          ["2", "529.982.247-25", "JA TEM OUTRO", "SIM", "Visual", "ATIVO", "POSTO A", "PORTEIRO", "JORNADA A"],
          ["3", "000.000.000-00", "CPF INVALIDO", "", "", "ATIVO", "", "", ""]]
mapa = {"111444777 35".replace(" ", ""): Pessoa(),
        "52998224725": Pessoa(jornada_id="OUTRA-JORNADA", cargo="AUXILIAR", pcd=False)}
a = vt.analisar(linhas, candidatos_por_cpf=mapa,
                jornadas_por_descricao={"jornada a": "J1"},
                postos_por_nome={"posto a": "P1"})
d1 = next(d for d in a.decisoes if d.cpf == "11144477735")
d2 = next(d for d in a.decisoes if d.cpf == "52998224725")
checar(d1.jornada_situacao == vt.PREENCHER and d1.jornada_id == "J1",
       "quem está sem jornada aqui recebe a do Tirvu")
checar(d2.jornada_situacao == vt.DIVERGE,
       "quem já tem OUTRA jornada não é sobrescrito — vira decisão humana")
checar(d1 in a.prontas and d2 in a.divergentes,
       "as duas listas separam o automático do que precisa de você")
checar(d2.pcd is True and d2.pcd_situacao == vt.DIVERGE,
       "PCD que discorda do portal também é decisão, não atropelo")
checar(a.sem_cpf == 1, "linha com CPF inválido é contada, não somem em silêncio")

# Cargo com caixa/acento diferentes é o MESMO cargo, não divergência.
a2 = vt.analisar([CABECALHO, ["9", "111.444.777-35", "X", "", "", "ATIVO", "", "Motorista", ""]],
                 candidatos_por_cpf={"11144477735": Pessoa(cargo="MOTORISTA")},
                 jornadas_por_descricao={}, postos_por_nome={})
checar(a2.decisoes[0].cargo_situacao == vt.IGUAL,
       "'Motorista' e 'MOTORISTA' são o mesmo cargo — divergência falsa faria o "
       "RH conferir mil linhas à toa")

# Sem par: entra na fila COM a contagem de gente que depende.
a3 = vt.analisar([CABECALHO,
                  ["1", "111.444.777-35", "A", "", "", "ATIVO", "INEP ADM", "", "NAO EXISTE"],
                  ["2", "529.982.247-25", "B", "", "", "ATIVO", "INEP ADM", "", "NAO EXISTE"]],
                 candidatos_por_cpf={"11144477735": Pessoa(), "52998224725": Pessoa()},
                 jornadas_por_descricao={}, postos_por_nome={})
checar(a3.jornadas_sem_par.get("NAO EXISTE") == 2 and a3.lotacoes_sem_par.get("INEP ADM") == 2,
       "o que não casa vira fila com o número de pessoas afetadas")

# =================================================== 2. pela rota, gravando
print("\n[preview e aplicação pela rota]")
suf = uuid.uuid4().hex[:8]
# CPF gerado POR EXECUÇÃO: com valor fixo, a segunda rodada no mesmo banco
# encontra o candidato da rodada anterior com o mesmo CPF e o dicionário por
# CPF fica com um deles — o teste falharia sem defeito nenhum no código
# (a armadilha "teste que só passa em banco limpo", v2.14).
_d = uuid.uuid4().int
CPF_A = f"9{_d % 10**10:010d}"
CPF_B = f"8{(_d // 7) % 10**10:010d}"
with SessionLocal() as db:
    jornada = Jornada(descricao=f"VINCULO TESTE {suf} - 2A A 6A - 08H - 17H")
    posto = PostoServico(nome=f"POSTO VINCULO {suf}")
    db.add_all([jornada, posto])
    db.flush()
    db.add_all([
        Candidato(nome_completo=f"Vazio {suf}", cpf=CPF_A, situacao="ativo",
                  email=f"a{suf}@ex.com"),
        Candidato(nome_completo=f"Ocupado {suf}", cpf=CPF_B, situacao="ativo",
                  email=f"b{suf}@ex.com", cargo_funcao="CARGO ANTIGO"),
    ])
    db.commit()
    jid, pid = str(jornada.id), str(posto.id)
    desc, nome_posto = jornada.descricao, posto.nome

xlsx = planilha([
    ["1", CPF_A, f"Vazio {suf}", "SIM", "Visual", "ATIVO", nome_posto, "MOTORISTA", desc],
    ["2", CPF_B, f"Ocupado {suf}", "NÃO", "", "ATIVO", nome_posto, "CARGO NOVO", desc],
])
r = c.post("/api/rh/colaboradores/vinculos/preview", headers=H,
           files={"arquivo": ("colab.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
checar(r.status_code == 200, f"preview aceito ({r.status_code}) {r.text[:120]}")
prev = r.json()
nossos = [i for i in prev["itens"] if i["cpf"] in (CPF_A, CPF_B)]
checar(any(i["cpf"] == CPF_A for i in nossos), "quem está vazio entra em 'prontas'")
divergentes = [i for i in prev["itens_divergentes"] if i["cpf"] == CPF_B]
checar(len(divergentes) == 1 and divergentes[0]["cargo"]["situacao"] == "diverge",
       "quem tem cargo DIFERENTE fica fora do lote automático")

with SessionLocal() as db:
    antes = db.scalar(select(Candidato).where(Candidato.cpf == CPF_B))
    checar(antes.cargo_funcao == "CARGO ANTIGO",
           "o preview NÃO gravou nada — é proposta, não ação")

item_a = next(i for i in prev["itens"] if i["cpf"] == CPF_A)
r = c.post("/api/rh/colaboradores/vinculos/aplicar", headers=H, json={"itens": [{
    "cpf": CPF_A, "jornada_id": item_a["jornada"]["id"],
    "cargo_funcao": item_a["cargo"]["texto"], "posto_id": item_a["posto"]["id"],
    "pcd": item_a["pcd"]["valor"], "pcd_deficiencia": item_a["pcd"]["deficiencia"]}]})
checar(r.status_code == 200, f"aplicação aceita ({r.status_code})")
with SessionLocal() as db:
    p = db.scalar(select(Candidato).where(Candidato.cpf == CPF_A))
    checar(str(p.jornada_id) == jid, "jornada gravada")
    checar(str(p.posto_servico_id) == pid, "posto gravado")
    checar(p.cargo_funcao == "MOTORISTA", "cargo gravado")
    dp = db.get(DadosPessoais, p.id)
    checar(dp is not None and dp.pcd is True,
           "PCD gravado na ficha, criando o registro se ele não existia")
    b = db.scalar(select(Candidato).where(Candidato.cpf == CPF_B))
    checar(b.cargo_funcao == "CARGO ANTIGO",
           "quem NÃO foi enviado continua intocado")

# ============================================================ 3. sem N+1
print("\n[custo da análise]")
from sqlalchemy import event  # noqa: E402

from app.core.db import engine  # noqa: E402

contador = {"n": 0}
event.listen(engine, "before_cursor_execute", lambda *a, **k: contador.__setitem__("n", contador["n"] + 1))
pequena = planilha([["1", CPF_A, "x", "", "", "ATIVO", nome_posto, "MOTORISTA", desc]])
grande = planilha([["1", CPF_A, "x", "", "", "ATIVO", nome_posto, "MOTORISTA", desc]] * 40)
contador["n"] = 0
c.post("/api/rh/colaboradores/vinculos/preview", headers=H,
       files={"arquivo": ("p.xlsx", pequena, "application/vnd.ms-excel")})
poucas = contador["n"]
contador["n"] = 0
c.post("/api/rh/colaboradores/vinculos/preview", headers=H,
       files={"arquivo": ("g.xlsx", grande, "application/vnd.ms-excel")})
muitas = contador["n"]
checar(muitas <= poucas + 1,
       f"1 linha e 40 linhas custam o mesmo número de consultas ({poucas} para {muitas}) — "
       "com 1.156 pessoas, uma consulta por linha seria a diferença entre segundos e minutos")

# =============================== 4. a planilha real, quando está disponível
DOCS = pathlib.Path(__file__).resolve().parents[2] / "docs" / "modelos de arquivos exportados do tirvu"
real = next(iter(sorted(DOCS.glob("Colaboradores*.xlsx"))), None)
if real:
    print(f"\n[planilha real: {real.name}]")
    r = c.post("/api/rh/colaboradores/vinculos/preview", headers=H,
               files={"arquivo": (real.name, real.read_bytes(), "application/vnd.ms-excel")})
    checar(r.status_code == 200, f"planilha real aceita ({r.status_code})")
    p = r.json()
    print(f"       {p['linhas']} linhas · {p['prontas']} prontas · {p['divergentes']} divergentes "
          f"· {p['fora_da_base']} fora da base · {len(p['lotacoes_sem_par'])} lotações sem par")
    checar(p["linhas"] > 1000, f"leu a base inteira ({p['linhas']} linhas)")
    checar(len(p["lotacoes_sem_par"]) > 0,
           "as lotações abreviadas do Tirvu aparecem como fila, não como vínculo no chute")
    checar(all(l["pessoas"] > 0 for l in p["lotacoes_sem_par"]),
           "cada item da fila diz quantas pessoas dependem dele")

print()
if FALHAS:
    print(f"test_vinculo_tirvu: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_vinculo_tirvu: OK")
