"""O cargo cadastrado APARECE onde ele vai ser usado.

Defeito visto pelo Bruno em 2026-09-22, um dia depois da v3.21: *"o cargo recém
criado não aparece nas demais páginas, por exemplo, na página de admissões"*.

A causa é uma confusão de FONTES, criada por mim na própria v3.21:

| Tela | Grava em | Lê de |
|---|---|---|
| Cargos (nova) | `CargoTirvu` (de-para) | `CargoTirvu` |
| Convite de Admissões | — | `Candidato.cargo_funcao` |

`GET /rh/cargos` montava a lista só a partir de quem **OCUPA** o cargo, então
cargo recém-cadastrado ficava invisível até alguém ser admitido nele — **a
ordem inversa do trabalho**, porque se cadastra o cargo ANTES de admitir.

O sintoma engana: o cadastro funciona, a tela de Cargos mostra o registro, e
nada dá erro. Ele só some no lugar onde ia ser usado — a família do "documento
que não nasce" (v2.69) e do "worker que não roda" (v2.66), onde a ausência não
gera erro, gera silêncio.

O que este teste protege:

1. **Cargo só no de-para APARECE no seletor** — é o defeito relatado.
2. **Cargo que alguém ocupa continua aparecendo** (nada regrediu) e vem
   ANTES, porque a lista é ordenada por frequência.
3. **O mesmo cargo nas duas fontes não vira DUAS entradas** — casa por texto
   normalizado, a mesma chave do export ("Vigia" e "vigia " são um só).
4. **O rótulo de quem tem gente vem da FICHA**, não do de-para: é o texto que o
   export leva ao Tirvu, e trocá-lo mudaria a planilha sem ninguém pedir.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_cargos_seletor.py
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
    """Emoji em mensagem de falha quebra o teste no console do Windows (v3.15)."""
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
assert _login.status_code == 200, (
    f"login falhou ({_login.status_code}) — confira RH_ADMIN_EMAIL/RH_ADMIN_PASSWORD.")
H = {"Authorization": f"Bearer {_login.json()['token']}"}

# Sufixo por execução: `cargo_normalizado` é UNIQUE, e nome fixo faria o teste
# passar só em banco limpo (v2.14).
SUFIXO = uuid.uuid4().hex[:8]
SO_DEPARA = f"Cargo So No Depara {SUFIXO}"


def _limpar():
    from app.services.export_tirvu import normalizar_cargo
    with SessionLocal() as db:
        for nome in (SO_DEPARA,):
            m = db.scalar(select(CargoTirvu).where(
                CargoTirvu.cargo_normalizado == normalizar_cargo(nome)))
            if m:
                db.delete(m)
        db.commit()


_limpar()

print("\n=== 1. cargo cadastrado SÓ no de-para aparece no seletor ===")
r = c.put("/api/rh/cargos-tirvu", headers=H,
          json={"cargo_rotulo": SO_DEPARA, "tirvu_id": "8801", "cbo": "514225"})
checar(r.status_code == 200, f"cadastro aceito (veio {r.status_code})")

lista = c.get("/api/rh/cargos", headers=H).json()["cargos"]
nomes = [x["nome"] for x in lista]
checar(SO_DEPARA in nomes,
       f"o cargo recem-cadastrado APARECE no seletor de Admissoes "
       f"(o defeito: ficava invisivel ate alguem ser admitido nele)")

item = next((x for x in lista if x["nome"] == SO_DEPARA), None)
checar(item is not None and item["pessoas"] == 0,
       f"entra com pessoas=0 (veio {item and item['pessoas']}) — vai para o fim "
       f"da lista, sem competir com os que tem gente")

print("\n=== 2. quem OCUPA cargo continua aparecendo, e vem antes ===")
# Não cria candidato: usa o que a base real já tem — se não houver nenhum, o
# teste ANUNCIA em vez de falhar numa asserção que não fala da causa (v2.66).
com_gente = [x for x in lista if x["pessoas"] > 0]
if not com_gente:
    _reportar("  (pulado) a base nao tem ninguem com cargo preenchido")
else:
    checar(True, f"{len(com_gente)} cargo(s) com gente continuam na lista")
    primeiro = lista[0]
    checar(primeiro["pessoas"] >= com_gente[-1]["pessoas"],
           f"ordenado por frequencia: o 1o tem {primeiro['pessoas']} pessoa(s)")
    # O de-para não pode ter empurrado quem tem gente para depois de quem tem zero.
    posicao_zero = next((i for i, x in enumerate(lista) if x["pessoas"] == 0), len(lista))
    ultimo_com_gente = max(i for i, x in enumerate(lista) if x["pessoas"] > 0)
    checar(ultimo_com_gente < posicao_zero,
           "nenhum cargo com gente ficou DEPOIS de um cargo sem gente")

print("\n=== 3. o mesmo cargo nas duas fontes NAO duplica ===")
if com_gente:
    alvo = com_gente[0]
    antes = len([x for x in lista if x["nome"] == alvo["nome"]])
    # Cadastra no de-para um cargo que JÁ tem gente, com caixa diferente.
    c.put("/api/rh/cargos-tirvu", headers=H,
          json={"cargo_rotulo": alvo["nome"].upper(), "tirvu_id": "8802"})
    lista2 = c.get("/api/rh/cargos", headers=H).json()["cargos"]
    iguais = [x for x in lista2 if x["nome"].strip().lower() == alvo["nome"].strip().lower()]
    checar(len(iguais) == 1,
           f"'{alvo['nome']}' aparece UMA vez (veio {len(iguais)}) — casa por "
           f"texto normalizado, como o export")
    checar(iguais and iguais[0]["nome"] == alvo["nome"],
           f"o rotulo vem da FICHA ({alvo['nome']!r}), nao do de-para em "
           f"CAIXA ALTA — e o texto que o export leva ao Tirvu")
    checar(iguais and iguais[0]["pessoas"] == alvo["pessoas"],
           f"a contagem de pessoas nao mudou (veio "
           f"{iguais and iguais[0]['pessoas']}, esperado {alvo['pessoas']})")
    # devolve o banco ao estado anterior
    c.put("/api/rh/cargos-tirvu", headers=H,
          json={"cargo_rotulo": alvo["nome"].upper(), "tirvu_id": ""})
else:
    _reportar("  (pulado) sem cargo com gente para testar a uniao")

_limpar()

print()
if FALHAS:
    _reportar(f"test_cargos_seletor: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        _reportar(f"  - {f}")
    raise SystemExit(1)
_reportar("test_cargos_seletor: OK")
