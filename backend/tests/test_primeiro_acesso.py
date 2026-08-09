"""Primeiro acesso: o sistema sem usuário cria o próprio administrador (v2.84).

Pedido do Bruno (2026-08-08):

    "esse email é real. está deixando um ponto de vulnerabilidade exposta no
     repositório do github. quero que tire isso agora e mais, coloque um
     cadastro, tipo guiado onde, no primeiro acesso, ali sejam coletados os
     dados e criados os dados cadastrais (…) mas lembre que é somente para o
     primeiro acesso."

O primeiro administrador nascia do `.env` (`RH_ADMIN_EMAIL`/`_PASSWORD`), o que
obrigava a escrever uma senha em arquivo e publicava o endereço de quem opera o
sistema num repositório PÚBLICO.

**O que este teste protege é o PORTÃO.** As duas rotas são públicas por
necessidade — não há quem autentique antes de existir o primeiro usuário —,
então a única coisa que separa "instalação nova se configurando" de "qualquer um
cria administrador na produção" é a checagem `nenhum usuário no banco`. Se ela
cair, nada na tela denuncia: a tela continua idêntica, e o defeito só aparece no
dia em que alguém a encontrar.

Roda contra um banco LIMPO (sem nenhum `UsuarioRH`) — é o único estado em que o
fluxo existe. O teste cria o admin e, a partir daí, exercita o portão fechado.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_primeiro_acesso.py
"""

import os
import sys
import uuid

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55498/admissao")
os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")
# Vazios DE PROPÓSITO: é o padrão da v2.84 e o que faz a tela de primeiro acesso
# existir. Preenchidos, o `bootstrap` criaria o admin e o fluxo nem apareceria.
os.environ["RH_ADMIN_EMAIL"] = ""
os.environ["RH_ADMIN_PASSWORD"] = ""

from fastapi.testclient import TestClient      # noqa: E402
from sqlalchemy import select                  # noqa: E402

from app.main import app                       # noqa: E402
from app.core.db import SessionLocal           # noqa: E402
from app.models.usuario_rh import UsuarioRH    # noqa: E402

# `raise_server_exceptions=False` para que um 500 vire RESPOSTA e possa ser
# reprovado: com a exceção repropagada, a mutação MATA o teste no meio e a saída
# vazia passa por sucesso (lição da v2.72.2).
c = TestClient(app, raise_server_exceptions=False)

FALHAS: list[str] = []


def checar(condicao: bool, descricao: str) -> None:
    print(("  ok    " if condicao else "  FALHA ") + descricao)
    if not condicao:
        FALHAS.append(descricao)


# --- pré-condição: o banco precisa estar SEM usuários ----------------------
with SessionLocal() as db:
    existentes = db.scalars(select(UsuarioRH)).all()

if existentes:
    print(f"\nPRÉ-CONDIÇÃO QUEBRADA: o banco tem {len(existentes)} usuário(s).")
    print("Este teste descreve a instalação NOVA e precisa de um banco limpo:")
    print("  docker run -d --name pg-pa -e POSTGRES_USER=admissao "
          "-e POSTGRES_PASSWORD=admissao -e POSTGRES_DB=admissao "
          "-p 55498:5432 postgres:16-alpine")
    print("  DATABASE_URL=postgresql+psycopg://admissao:admissao@localhost:55498/"
          "admissao alembic upgrade head")
    sys.exit(1)


print("\n1. com o banco vazio, o sistema PEDE o primeiro acesso")
r = c.get("/api/rh/auth/primeiro-acesso")
checar(r.status_code == 200, f"a rota responde 200 (veio {r.status_code})")
checar(r.json().get("necessario") is True,
       "e diz que o primeiro acesso é necessário")
# Não pode vazar mais que o booleano: quem pergunta ainda não tem sessão.
checar(set(r.json()) == {"necessario"},
       f"devolve SÓ o booleano, sem nome/e-mail/contagem (veio {sorted(r.json())})")


print("\n2. o cadastro recusa dado que deixaria o dono trancado para fora")
r = c.post("/api/rh/auth/primeiro-acesso",
           json={"nome": "  ", "email": "dono@exemplo.com.br", "senha": "senha-boa-123"})
checar(r.status_code == 422 and r.json().get("detail") == "nome_obrigatorio",
       f"nome em branco: 422 nome_obrigatorio (veio {r.status_code} "
       f"{r.json().get('detail')})")

r = c.post("/api/rh/auth/primeiro-acesso",
           json={"nome": "Dono do Sistema", "email": "dono@exemplo.com.br",
                 "senha": "1234"})
checar(r.status_code == 422 and r.json().get("detail") == "senha_curta_minimo_8",
       f"senha curta: 422 senha_curta_minimo_8 (veio {r.status_code} "
       f"{r.json().get('detail')})")

# Ninguém foi criado por engano nas recusas acima.
with SessionLocal() as db:
    checar(db.scalar(select(UsuarioRH).limit(1)) is None,
           "nenhum usuário foi criado pelas tentativas recusadas")


print("\n3. o cadastro cria o administrador E já devolve a sessão")
EMAIL = f"dono-{uuid.uuid4().hex[:8]}@exemplo.com.br"
r = c.post("/api/rh/auth/primeiro-acesso",
           json={"nome": "maria de fátima souza", "email": EMAIL.upper(),
                 "senha": "senha-boa-123"})
checar(r.status_code == 200, f"responde 200 (veio {r.status_code}: {r.text[:120]})")
corpo = r.json() if r.status_code == 200 else {}
checar(bool(corpo.get("token")),
       "devolve o token da sessão — a pessoa entra sem digitar a senha de novo")
# `capitalizar_nome`, não `.title()`: o `.title()` produziria "Maria De Fátima"
# (regra da v2.54). O nome do dono do sistema aparece no painel inteiro.
checar(corpo.get("nome") == "Maria de Fátima Souza",
       f"e o nome vem capitalizado direito (veio {corpo.get('nome')!r})")

with SessionLocal() as db:
    u = db.scalar(select(UsuarioRH).where(UsuarioRH.email == EMAIL.lower()))
checar(u is not None, "o usuário existe no banco")
checar(u is not None and u.ativo, "e nasce ATIVO — senão o dono não entraria")
checar(u is not None and u.senha_hash and "senha-boa-123" not in u.senha_hash,
       "a senha foi gravada como HASH, nunca em claro")

# O token devolvido tem que abrir o painel de verdade — não basta ser string.
if corpo.get("token"):
    r = c.get("/api/rh/me", headers={"Authorization": f"Bearer {corpo['token']}"})
    checar(r.status_code == 200,
           f"o token abre o painel (GET /rh/me veio {r.status_code})")


print("\n4. O PORTÃO FECHA — e é isto que separa 'instalação nova' de porta aberta")
r = c.get("/api/rh/auth/primeiro-acesso")
checar(r.json().get("necessario") is False,
       "a consulta passa a dizer que NÃO é mais necessário")

r = c.post("/api/rh/auth/primeiro-acesso",
           json={"nome": "Invasor", "email": "invasor@exemplo.com.br",
                 "senha": "senha-boa-123"})
checar(r.status_code == 409 and r.json().get("detail") == "primeiro_acesso_ja_feito",
       f"criar um SEGUNDO administrador por ali: 409 primeiro_acesso_ja_feito "
       f"(veio {r.status_code} {r.json().get('detail')})")

with SessionLocal() as db:
    quantos = len(db.scalars(select(UsuarioRH)).all())
checar(quantos == 1,
       f"e o banco continua com UM usuário (tem {quantos}) — a recusa não é só "
       f"do status code, nada foi criado")


print("\n5. o login normal funciona com a credencial recém-criada")
r = c.post("/api/rh/auth/login", json={"email": EMAIL.lower(), "senha": "senha-boa-123"})
checar(r.status_code == 200 and bool(r.json().get("token")),
       f"entra pelo login de sempre (veio {r.status_code})")
r = c.post("/api/rh/auth/login", json={"email": EMAIL.lower(), "senha": "outra-senha-9"})
checar(r.status_code == 401,
       f"e a senha errada continua sendo recusada (veio {r.status_code})")


print()
if FALHAS:
    print(f"test_primeiro_acesso: {len(FALHAS)} FALHA(S)")
    for f in FALHAS:
        print(f"  - {f}")
    sys.exit(1)
print("test_primeiro_acesso: OK")
