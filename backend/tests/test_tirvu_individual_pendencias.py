"""O export individual do Tirvu não baixa planilha furada em silêncio (v2.42).

Feedback de campo do Bruno em 2026-08-01: ele exportou pelo botão da FICHA e
recebeu a planilha com posto, cargo e jornada em branco — sem um aviso sequer.
A pré-checagem existia desde a v1.82, mas só no caminho em massa
(`/rh/colaboradores/tirvu-pendencias`); o botão individual (`revisao.py`)
montava o arquivo e devolvia.

O que torna isso grave é o comportamento do Tirvu: ele **aceita a célula vazia
calado**. Ninguém descobre no upload — descobre semanas depois, quando o
colaborador está lá com o vínculo torto.

O que este teste protege:

1. **A resposta DIZ o que ficou faltando** (`X-Tirvu-Pendencias`), com as
   mesmas regras do export em massa. Quem chama a rota direto também é avisado,
   não só quem passa pela tela.
2. **O download continua acontecendo** — às vezes se quer a planilha
   incompleta mesmo, e travar seria trocar um problema por outro.
3. **A pendência vai para a AUDITORIA**: "exportei e não sabia" deixa de ser
   uma possibilidade.
4. **Sem pendência, o cabeçalho diz "nenhuma"** — ausência de aviso não pode
   ser ambígua entre "está tudo certo" e "ninguém conferiu".
5. **O cabeçalho é ASCII**: "Descrição da Jornada" com acento derrubaria a
   resposta inteira (HTTP não aceita acento em header).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_tirvu_individual_pendencias.py
"""

import os
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
from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.evento import EventoAuditoria  # noqa: E402
from app.models.candidato import Candidato, Jornada, PostoServico  # noqa: E402
from app.models.ficha import DocumentosIdentificacao  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@exemplo.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

suf = uuid.uuid4().hex[:8]

# ------------------------------------------- pessoa com o cadastro pela metade
# É o caso real: veio do Tirvu ou foi efetivada, mas os IDs de posto/cargo/
# jornada nunca foram cadastrados aqui.
with SessionLocal() as db:
    posto = PostoServico(nome=f"POSTO SEM ID {suf}")           # sem tirvu_id
    jornada = Jornada(descricao=f"JORNADA SEM ID {suf}")       # sem tirvu_id
    db.add_all([posto, jornada])
    db.flush()
    incompleta = Candidato(nome_completo=f"Faltando Tudo {suf}",
                           email=f"falta{suf}@ex.com", cpf=f"3{uuid.uuid4().int % 10**10:010d}",
                           situacao="ativo", posto_servico_id=posto.id,
                           jornada_id=jornada.id, cargo_funcao="CARGO SEM DE-PARA")
    db.add(incompleta)
    db.commit()
    id_incompleta = str(incompleta.id)

print("\n[a resposta diz o que ficou faltando]")
r = c.get(f"/api/rh/candidatos/{id_incompleta}/exportar-tirvu", headers=H)
checar(r.status_code == 200, f"o download ACONTECE ({r.status_code}) — travar seria "
       "trocar um problema por outro")
aviso = r.headers.get("X-Tirvu-Pendencias", "")
checar(aviso and aviso != "nenhuma", f"e vem acompanhado do que falta: {aviso!r}")
for esperado in ("Posto", "Cargo", "Jornada"):
    checar(esperado.lower() in aviso.lower(),
           f"{esperado} aparece entre as pendências")
checar(aviso.isascii(),
       "o cabeçalho é ASCII — acento em header HTTP derruba a resposta inteira")
checar(len(r.content) > 1000, "e a planilha em si veio inteira")

print("\n[a pendência fica registrada]")
with SessionLocal() as db:
    ev = db.scalars(select(EventoAuditoria)
                    .where(EventoAuditoria.acao == "tirvu_exportado")
                    .order_by(EventoAuditoria.criado_em.desc()).limit(5)).all()
    nosso = next((e for e in ev if (e.detalhe or {}).get("candidato") == id_incompleta), None)
    checar(nosso is not None, "o export foi auditado")
    checar(nosso is not None and (nosso.detalhe or {}).get("pendencias"),
           "com a LISTA de pendências junto — 'exportei e não sabia' deixa de "
           "ser possível")

print("\n[mesma checagem do export em massa]")
r = c.get(f"/api/rh/colaboradores/tirvu-pendencias?ids={id_incompleta}", headers=H)
faltas_massa = r.json()["com_pendencia"][0]["faltam"]
do_individual = [x.strip() for x in aviso.split(",")]
checar(len(faltas_massa) == len(do_individual),
       f"o individual acusa o MESMO tanto que o massa ({len(do_individual)} x "
       f"{len(faltas_massa)}) — duas contas diferentes para a mesma planilha "
       "seria pior que nenhuma")

print("\n[cadastro completo: nenhuma pendência]")
with SessionLocal() as db:
    posto2 = PostoServico(nome=f"POSTO COM ID {suf}", tirvu_id="49")
    jornada2 = Jornada(descricao=f"JORNADA COM ID {suf}", tirvu_id="246")
    db.add_all([posto2, jornada2])
    db.flush()
    from app.models.candidato import CargoTirvu
    from app.services.export_tirvu import normalizar_cargo
    cargo = f"ANALISTA {suf}"
    db.add(CargoTirvu(cargo_normalizado=normalizar_cargo(cargo), cargo_rotulo=cargo,
                      tirvu_id="50"))
    cpf_ok = f"4{uuid.uuid4().int % 10**10:010d}"
    completa = Candidato(nome_completo=f"Cadastro Completo {suf}",
                         email=f"ok{suf}@ex.com", cpf=cpf_ok, situacao="ativo",
                         posto_servico_id=posto2.id, jornada_id=jornada2.id,
                         cargo_funcao=cargo, registra_ponto=True,
                         data_admissao="01/08/2026", matricula=f"999{suf[:4]}")
    db.add(completa)
    db.flush()
    db.add(DocumentosIdentificacao(candidato_id=completa.id, cpf=cpf_ok,
                                   pis_nis_pasep="12345678901"))
    db.commit()
    id_completa = str(completa.id)

r = c.get(f"/api/rh/candidatos/{id_completa}/exportar-tirvu", headers=H)
checar(r.headers.get("X-Tirvu-Pendencias") == "nenhuma",
       f"cadastro completo sai sem pendência, e DIZ isso "
       f"({r.headers.get('X-Tirvu-Pendencias')!r}) — silêncio seria ambíguo "
       "entre 'está tudo certo' e 'ninguém conferiu'")

print()
if FALHAS:
    print(f"test_tirvu_individual_pendencias: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_tirvu_individual_pendencias: OK")
