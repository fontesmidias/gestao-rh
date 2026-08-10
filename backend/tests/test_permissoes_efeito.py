"""A permissão NEGA de verdade — não basta estar declarada (v2.86).

O `test_permissoes_declaradas.py` é estrutural: prova que toda rota `/rh/*`
declara uma permissão. Ele não prova que a declaração SURTE EFEITO — e essa é
exatamente a diferença que este projeto já pagou caro em outras frentes: o teste
que exercita a função interna e passa verde enquanto o caminho real está quebrado
(v2.68), a asserção que confere só o status code enquanto a proteção sumiu
(v2.80), o teste que compara a resposta com ela mesma (v2.64).

Aqui a asserção é sobre o COMPORTAMENTO: um usuário com papel restrito leva 403
numa rota que ele não pode, e 200 numa que ele pode. E, como manda a lição da
v2.84, também se afirma sobre o ESTADO — a mutação que remove o `exige` de uma
rota destrutiva precisa fazer este teste FALHAR, não passar por outro caminho.
"""

import os
import sys
import uuid
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("DATABASE_URL",
                      "postgresql+psycopg://admissao:admissao@localhost:55432/admissao")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_senha  # noqa: E402
from app.main import app  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.services import permissoes as cat  # noqa: E402

# `raise_server_exceptions=False` para que um 500 vire RESPOSTA e possa ser
# reprovado por asserção, em vez de matar o script no meio — a lição da v2.72.2,
# onde a mutação que estourava no servidor produzia saída vazia que passava
# por sucesso.
cliente = TestClient(app, raise_server_exceptions=False)


def _criar(db, papel: str) -> tuple[str, str]:
    """Cria um usuário descartável com o papel pedido e devolve (email, senha)."""
    marca = uuid.uuid4().hex[:8]
    email = f"perm-{papel}-{marca}@exemplo.com.br"
    senha = "senha-teste-123"
    db.add(UsuarioRH(nome=f"Teste {papel}", email=email,
                     senha_hash=hash_senha(senha), papel=papel))
    db.commit()
    return email, senha


def _token(email: str, senha: str) -> str:
    r = cliente.post("/api/rh/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, (
        f"login falhou ({r.status_code}) para {email} — confira se a migration "
        f"do papel rodou e se a senha bate. Corpo: {r.text[:200]}")
    return r.json()["token"]


def main() -> int:
    falhas: list[str] = []
    db = SessionLocal()
    try:
        # --- Papel estreito: recepção -------------------------------------
        email, senha = _criar(db, "recepcao")
        cab = {"Authorization": f"Bearer {_token(email, senha)}"}

        # 1. Rota que a recepção NÃO pode: listar a base de colaboradores.
        r = cliente.get("/api/rh/colaboradores", headers=cab)
        if r.status_code != 403:
            falhas.append(
                f"recepção deveria levar 403 em GET /rh/colaboradores, "
                f"veio {r.status_code} — a permissão não está surtindo efeito.")
        else:
            corpo = r.json().get("detail") or {}
            # Afirmar sobre o MOTIVO, não só sobre o código: um 403 genérico
            # também viria de outra causa, e o teste passaria sem provar nada
            # (a lição da v2.80).
            if corpo.get("permissao") != "colaboradores:ler":
                falhas.append(
                    f"o 403 não nomeia a permissão que falta: {corpo!r}")

        # 2. Rota DESTRUTIVA que a recepção não pode: desligar alguém.
        r = cliente.post(f"/api/rh/colaboradores/{uuid.uuid4()}/desligar",
                         headers=cab, json={"data_desligamento": "2026-08-10"})
        if r.status_code != 403:
            falhas.append(
                f"recepção deveria levar 403 ao DESLIGAR, veio {r.status_code}. "
                "Atenção: 404 aqui significa que a autorização passou e a rota "
                "só não achou o registro — ou seja, a proteção NÃO existe.")

        # --- Papel amplo: RH ----------------------------------------------
        email_rh, senha_rh = _criar(db, "rh")
        cab_rh = {"Authorization": f"Bearer {_token(email_rh, senha_rh)}"}

        # 3. O RH PODE listar colaboradores — a permissão não pode negar tudo.
        r = cliente.get("/api/rh/colaboradores", headers=cab_rh)
        if r.status_code != 200:
            falhas.append(
                f"RH deveria conseguir listar colaboradores, veio {r.status_code} "
                f"— permissão restritiva demais. Corpo: {r.text[:200]}")

        # 4. O RH NÃO gere usuários: é o degrau que separa RH de administrador.
        r = cliente.get("/api/rh/usuarios", headers=cab_rh)
        if r.status_code != 403:
            falhas.append(
                f"RH deveria levar 403 em GET /rh/usuarios, veio {r.status_code} "
                "— qualquer pessoa do RH poderia criar administrador.")

        # --- Superadmin ----------------------------------------------------
        email_su, senha_su = _criar(db, cat.PAPEL_SUPERADMIN)
        cab_su = {"Authorization": f"Bearer {_token(email_su, senha_su)}"}

        # 5. O superadmin passa em tudo, inclusive na gestão de usuários.
        r = cliente.get("/api/rh/usuarios", headers=cab_su)
        if r.status_code != 200:
            falhas.append(
                f"superadmin deveria acessar /rh/usuarios, veio {r.status_code}. "
                "Ele NÃO consulta lista de permissões — se falhou aqui, o "
                "atalho de `pode()` quebrou e módulo novo deixará de nascer "
                "liberado para ele.")

        # 6. Perfil próprio funciona para QUALQUER papel, inclusive o estreito:
        #    exigir permissão aqui impediria alguém de trocar a própria senha.
        r = cliente.get("/api/rh/me", headers=cab)
        if r.status_code != 200:
            falhas.append(
                f"recepção deveria acessar o próprio perfil, veio {r.status_code}.")

        # 7. Sem token nenhum continua 401 (autenticação), não 403.
        r = cliente.get("/api/rh/colaboradores")
        if r.status_code != 401:
            falhas.append(
                f"sem token deveria ser 401, veio {r.status_code} — 401 e 403 "
                "dizem coisas diferentes a quem depura.")

        # --- Travas de administração de papéis -----------------------------
        # 8. Papel de fábrica não se apaga: a instalação perderia o "rh" e
        #    ninguém teria como recriá-lo com as permissões certas.
        r = cliente.get("/api/rh/papeis", headers=cab_su)
        if r.status_code != 200:
            falhas.append(f"superadmin não listou papéis: {r.status_code}")
        else:
            ids = {p["chave"]: p["id"] for p in r.json()}
            d = cliente.delete(f"/api/rh/papeis/{ids['rh']}", headers=cab_su)
            if d.status_code != 409:
                falhas.append(
                    f"apagar papel de fábrica deveria dar 409, veio {d.status_code}")
            # 9. O superadmin não se edita — é a porta que não pode fechar por
            #    dentro. Sem isso, tirar as permissões dele trancaria o sistema.
            e = cliente.put(f"/api/rh/papeis/{ids['superadmin']}", headers=cab_su,
                            json={"rotulo": "x", "permissoes": []})
            if e.status_code != 409:
                falhas.append(
                    f"editar o papel superadmin deveria dar 409, veio {e.status_code}")

        # 10. Papel inexistente é recusado na ATRIBUIÇÃO: gravá-lo deixaria a
        #     pessoa sem acesso nenhum, com 403 em tudo e nada explicando.
        r = cliente.post("/api/rh/usuarios", headers=cab_su, json={
            "nome": "Fulano", "email": f"x-{uuid.uuid4().hex[:8]}@exemplo.com.br",
            "senha": "senha-teste-123", "papel": "papel-que-nao-existe"})
        if r.status_code != 422:
            falhas.append(
                f"papel inexistente deveria dar 422, veio {r.status_code}")
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — 10 asserções: a permissão nega, libera, nomeia o que falta,\n"
          "     e as travas de administração de papéis seguram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
