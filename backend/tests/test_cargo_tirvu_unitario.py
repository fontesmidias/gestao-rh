"""CRUD de UM cargo com CBO (2026-09-22).

Feedback do Bruno: *"quando o rh quer subir apenas um cargo, daí seria
interessante ter uma funcionalidade para isso, o CRUD, na vdd ne"*. Até aqui,
cadastrar um cargo exigia o ritual inteiro do lote — abrir o Tirvu, selecionar,
copiar, colar no Bloco de Notas, salvar, subir — para gravar duas colunas.

O defeito que este teste tranca é mais silencioso que a falta de conveniência.
O `PUT /rh/cargos-tirvu` **não tinha campo `cbo`**, enquanto o lote
(`confirmar-cargos`) gravava. Ou seja: o cargo cadastrado à mão nascia sem a
ÚNICA informação que distingue homônimo — nos dados reais, "AUXILIAR DE
SERVIÇOS GERAIS" é 514225 (limpeza) e 763125 (produção), com 87 pessoas usando
o mesmo texto. Nada denunciava: a coluna ficava vazia, e a tela seguinte pedia
a decisão sobre qual ID usar escondendo o que a fundamenta.

O que este teste protege:

1. **O CBO é gravado pelo caminho unitário** — a mutação que remove o campo do
   `CargoTirvuIn` faz a coluna nascer nula, e é exatamente o estado anterior.
2. **CBO vazio NÃO apaga o que já estava** — mesma regra do lote. Quem edita só
   o ID pelo teclado não pode perder por omissão o CBO que a importação trouxe;
   perder dado por omissão é pior que não atualizar.
3. **O GET devolve o CBO** — ele já era gravado pelo lote e nunca chegava à
   tela. Sem isto, a página mostra a coluna sempre vazia e o defeito volta com
   outra cara.
4. **ID vazio continua REMOVENDO o de-para** — é como o RH desfaz, e o export
   volta a acusar pendência (comportamento antigo, que não pode regredir).

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_cargo_tirvu_unitario.py
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
from app.models.candidato import CargoTirvu  # noqa: E402

FALHAS = []


def _reportar(texto):
    """Emoji em mensagem de falha quebra o teste no console do Windows (v3.15):
    `UnicodeEncodeError` em cp1252 mata o script ANTES de mostrar a causa —
    justamente quando ela importa."""
    try:
        print(texto)
    except UnicodeEncodeError:
        print(texto.encode("ascii", "replace").decode("ascii"))


def checar(condicao, descricao):
    _reportar(("  ok   " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


c = TestClient(app)
_login = c.post("/api/rh/auth/login",
                json={"email": os.environ["RH_ADMIN_EMAIL"],
                      "senha": os.environ["RH_ADMIN_PASSWORD"]})
# Login que falha aqui vira `KeyError: 'token'`, erro que não fala da causa e
# manda procurar no lugar errado (v2.71). Afirma antes, com o que resolve.
assert _login.status_code == 200, (
    f"login falhou ({_login.status_code}) — confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD. "
    f"Lembre: `criar_admin_inicial` só cria o admin do .env com a tabela VAZIA.")
H = {"Authorization": f"Bearer {_login.json()['token']}"}

# Cargo com sufixo aleatório: `cargo_normalizado` é UNIQUE, e nome fixo faria o
# teste passar só em banco limpo (v2.14) — a 2ª execução casaria no registro da
# 1ª e verificaria um estado que ela mesma criou.
CARGO = f"AUXILIAR DE TESTE {uuid.uuid4().hex[:8]}"


def _no_banco():
    from app.services.export_tirvu import normalizar_cargo
    with SessionLocal() as db:
        return db.scalar(select(CargoTirvu).where(
            CargoTirvu.cargo_normalizado == normalizar_cargo(CARGO)))


print("\n=== 1. cadastrar UM cargo com CBO ===")
r = c.put("/api/rh/cargos-tirvu", headers=H,
          json={"cargo_rotulo": CARGO, "tirvu_id": "777", "cbo": "514225"})
checar(r.status_code == 200, f"a rota aceita o cadastro unitário (veio {r.status_code})")
checar(r.json().get("cbo") == "514225",
       f"a resposta devolve o CBO gravado (veio {r.json().get('cbo')!r})")

reg = _no_banco()
# A asserção de ESTADO é a que pega a mutação: sem ela, remover o campo `cbo`
# do schema devolveria 200 igual e o teste passaria com o defeito presente
# (v2.84 — "o teste afirma sobre o ESTADO").
checar(reg is not None, "o de-para foi criado no banco")
checar(reg is not None and reg.cbo == "514225",
       f"o CBO está GRAVADO na coluna (veio {getattr(reg, 'cbo', None)!r}) "
       f"— sem ele, homônimo fica indistinguível")

print("\n=== 2. o GET devolve o CBO para a tela ===")
lista = c.get("/api/rh/cargos-tirvu", headers=H).json()
linha = next((x for x in lista if x["cargo_rotulo"] == CARGO), None)
checar(linha is not None, "o cargo aparece na listagem")
checar(linha is not None and linha.get("cbo") == "514225",
       f"a listagem traz o CBO (veio {linha.get('cbo')!r} — a tela mostraria coluna vazia)")

print("\n=== 3. CBO vazio NÃO apaga o que já estava (regra do lote) ===")
c.put("/api/rh/cargos-tirvu", headers=H,
      json={"cargo_rotulo": CARGO, "tirvu_id": "888", "cbo": ""})
reg = _no_banco()
checar(reg is not None and reg.tirvu_id == "888", "o ID foi atualizado")
checar(reg is not None and reg.cbo == "514225",
       f"o CBO anterior CONTINUA gravado (veio {getattr(reg, 'cbo', None)!r}) — quem edita "
       f"só o ID não pode perder por omissão o CBO que a importação trouxe")

print("\n=== 4. CBO omitido do corpo também não apaga ===")
c.put("/api/rh/cargos-tirvu", headers=H, json={"cargo_rotulo": CARGO, "tirvu_id": "999"})
reg = _no_banco()
checar(reg is not None and reg.cbo == "514225",
       f"corpo SEM a chave `cbo` preserva o gravado (veio {getattr(reg, 'cbo', None)!r})")

print("\n=== 5. ID vazio continua REMOVENDO o de-para (não regrediu) ===")
r = c.put("/api/rh/cargos-tirvu", headers=H,
          json={"cargo_rotulo": CARGO, "tirvu_id": ""})
checar(r.status_code == 200, f"a remoção responde 200 (veio {r.status_code})")
checar(_no_banco() is None,
       "o de-para saiu do banco — é assim que o RH desfaz, e o export volta a "
       "acusar pendência")

print()
if FALHAS:
    _reportar(f"test_cargo_tirvu_unitario: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        _reportar(f"  - {f}")
    raise SystemExit(1)
_reportar("test_cargo_tirvu_unitario: OK")
