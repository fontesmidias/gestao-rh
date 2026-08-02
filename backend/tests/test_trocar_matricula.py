"""Trocar a matrícula sem desligar a pessoa do próprio histórico (v2.45).

Pedido do Bruno em 2026-08-01: *"ter a opção de trocar o número da matrícula de
um admitido/colaborador"*.

O cuidado não é burocracia. A matrícula é a **chave** com que o import de ponto
do Tirvu encontra a pessoa (`desempenho.py::_casar_matricula`). Trocar o número
sem guardar o antigo partiria o histórico de frequência dela em dois — e uma
planilha de período anterior, que ainda traz a matrícula velha, deixaria de
casar. Sem erro nenhum na tela: o registro simplesmente vira órfão.

Perguntado sobre o que fazer, o Bruno escolheu **levar o histórico junto**.

O que este teste protege:

1. **A matrícula antiga fica guardada** e o ponto importado com ela continua
   caindo na pessoa certa.
2. **Duas pessoas não podem ter a mesma matrícula** — indistinguível de uma
   pessoa com duas, e o ponto passaria a cair na errada. A comparação é
   NORMALIZADA: "003035" e "3035" são a mesma matrícula para o Tirvu.
3. **Motivo é obrigatório** (linha vermelha do projeto: ação manual do RH sai
   com motivo) e tudo vai para a auditoria, com o de para para.
4. **A matrícula ATUAL tem precedência** sobre a antiga de outra pessoa: se um
   número foi reciclado, quem o usa hoje ganha.
5. **Trocar várias vezes acumula** — ninguém troca de matrícula uma vez só na
   vida.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_trocar_matricula.py
"""

import os
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
from sqlalchemy import select  # noqa: E402

from app.api.desempenho import _casar_matricula  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.candidato import Candidato  # noqa: E402
from app.models.evento import EventoAuditoria  # noqa: E402

FALHAS = []


def checar(condicao, descricao):
    print(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
H = {"Authorization": f"Bearer {c.post('/api/rh/auth/login', json={'email': 'rh@greenhousedf.com.br', 'senha': 'senha-teste-123'}).json()['token']}"}

suf = uuid.uuid4().hex[:6]
# Matrículas SÓ COM DÍGITOS: `matricula_norm` (import de ponto) descarta
# qualquer outro caractere, então uma matrícula com letras casaria por engano
# com outra que tivesse os mesmos números. Aqui o teste tem que usar o mesmo
# formato do mundo real — a matrícula do Tirvu é numérica.
_n = uuid.uuid4().int % 10**5
VELHA = f"77{_n:05d}"
NOVA = f"88{_n:05d}"
DE_OUTRO = f"99{_n:05d}"

with SessionLocal() as db:
    pessoa = Candidato(nome_completo=f"Troca Matricula {suf}", situacao="ativo",
                       email=f"troca{suf}@ex.com", cpf=f"5{uuid.uuid4().int % 10**10:010d}",
                       matricula=VELHA)
    outro = Candidato(nome_completo=f"Outro {suf}", situacao="ativo",
                      email=f"outro{suf}@ex.com", cpf=f"6{uuid.uuid4().int % 10**10:010d}",
                      matricula=DE_OUTRO)
    db.add_all([pessoa, outro])
    db.commit()
    pid, oid = str(pessoa.id), str(outro.id)

# ============================================================ 1. a troca
print("\n[a troca guarda o número antigo]")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": NOVA, "motivo": "corrigindo digitação do cadastro"})
checar(r.status_code == 200, f"a troca é aceita ({r.status_code}) {r.text[:120]}")
checar(r.json()["matricula"] == NOVA, "a nova matrícula está valendo")
# `or []`: sem isto, remover a guarda do histórico derruba o teste com
# TypeError em vez de dizer QUAL garantia caiu — e mensagem de falha é o que
# serve a quem lê isso daqui a meses (lição da v2.39).
checar(VELHA in (r.json().get("matriculas_anteriores") or []),
       f"e a anterior fica guardada: {r.json().get('matriculas_anteriores')}")

# ======================== 2. o ponto antigo continua achando a pessoa
print("\n[o ponto de antes continua sendo dela]")
with SessionLocal() as db:
    achado = _casar_matricula(db, VELHA.lstrip("0"))
    checar(achado is not None and str(achado.id) == pid,
           "uma planilha de período anterior, com a matrícula VELHA, ainda casa "
           "com a pessoa — sem isso o histórico de frequência dela se partiria "
           "em dois no dia da troca")
    achado_novo = _casar_matricula(db, NOVA.lstrip("0"))
    checar(achado_novo is not None and str(achado_novo.id) == pid,
           "e a nova também casa, claro")
    # Zeros à esquerda: a planilha do Tirvu é inconsistente nisso.
    checar(_casar_matricula(db, f"000{NOVA}".lstrip("0")) is not None,
           "com zeros à esquerda continua casando (regra do import de ponto)")

# ================================================= 3. unicidade e guardas
print("\n[o que a troca recusa]")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": DE_OUTRO, "motivo": "tentando duplicar"})
checar(r.status_code == 409 and r.json()["detail"] == "matricula_em_uso",
       f"matrícula de outra pessoa é recusada ({r.status_code}) — duas pessoas "
       "com o mesmo número tornam impossível saber de quem é o ponto")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": f"00{DE_OUTRO}", "motivo": "com zeros à esquerda"})
checar(r.status_code == 409,
       "e com zeros à esquerda também — '003035' e '3035' são a MESMA matrícula "
       "para o Tirvu")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": f"{NOVA}X", "motivo": ""})
checar(r.status_code == 422 and r.json()["detail"] == "motivo_obrigatorio",
       "sem motivo, não troca — ação manual do RH sai com motivo")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": "", "motivo": "vazia"})
checar(r.status_code == 422, "matrícula vazia é recusada")
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": NOVA, "motivo": "mesma coisa"})
checar(r.status_code == 422 and r.json()["detail"] == "matricula_igual",
       "trocar pela mesma não vira registro de auditoria à toa")

# ================================================== 4. auditoria completa
print("\n[fica na auditoria com o de para para]")
with SessionLocal() as db:
    ev = db.scalars(select(EventoAuditoria).where(
        EventoAuditoria.acao == "matricula_alterada",
        EventoAuditoria.candidato_id == uuid.UUID(pid))).all()
    checar(len(ev) == 1, f"um evento ({len(ev)})")
    d = ev[0].detalhe if ev else {}
    checar(d.get("de") == VELHA and d.get("para") == NOVA,
           f"com o número antigo e o novo: {d.get('de')} para {d.get('para')}")
    checar(d.get("motivo") == "corrigindo digitação do cadastro",
           "e o motivo escrito pelo RH")
    checar("periodos_de_ponto" in d,
           "e quantos períodos de ponto estavam pendurados — o RH precisa saber "
           "o tamanho do que mexeu")

# ====================================== 5. trocar de novo ACUMULA histórico
print("\n[trocar de novo acumula]")
TERCEIRA = f"66{suf[:4]}"
r = c.put(f"/api/rh/colaboradores/{pid}/matricula", headers=H,
          json={"matricula": TERCEIRA, "motivo": "recontratação"})
checar(r.status_code == 200, "segunda troca aceita")
anteriores = r.json().get("matriculas_anteriores") or []
checar(VELHA in anteriores and NOVA in anteriores,
       f"as DUAS anteriores ficam guardadas ({anteriores}) — ninguém troca de "
       "matrícula uma vez só na vida")
with SessionLocal() as db:
    for antiga in (VELHA, NOVA):
        achado = _casar_matricula(db, antiga.lstrip("0"))
        checar(achado is not None and str(achado.id) == pid,
               f"e o ponto de {antiga} continua caindo nela")

# ============================== 6. a matrícula ATUAL tem precedência
print("\n[número reciclado: quem usa hoje ganha]")
r = c.put(f"/api/rh/colaboradores/{oid}/matricula", headers=H,
          json={"matricula": VELHA, "motivo": "número liberado, reaproveitado"})
checar(r.status_code == 200,
       f"outra pessoa PODE receber um número que ficou livre ({r.status_code})")
with SessionLocal() as db:
    achado = _casar_matricula(db, VELHA.lstrip("0"))
    checar(achado is not None and str(achado.id) == oid,
           "e o ponto passa a cair em quem usa o número HOJE, não em quem o "
           "usou no passado")

print()
if FALHAS:
    print(f"test_trocar_matricula: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_trocar_matricula: OK")
