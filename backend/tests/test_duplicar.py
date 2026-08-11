"""Duplicar: a cópia nasce SEM VALER e sem o que não pode ser copiado (v2.87).

Duplicar virou padrão da casa a pedido do Bruno — *"duplicar um existente e, a
partir dessa duplicata, editarmos o que tiver que editar para daí sim
ativarmos"*. O que este teste protege NÃO é a existência da rota (isso qualquer
revisão de código vê), e sim as três regras que, quando quebram, **não dão erro
em lugar nenhum**:

1. **A cópia nasce inativa.** Nascer ativa faz o cadastro passar a valer no
   instante em que é criado — uma vaga recebendo candidatura antes de alguém
   revisar os requisitos, um papel concedendo acesso antes de alguém conferir o
   que ele concede. O sistema funciona igual; o que muda é que passou a valer
   algo que ninguém revisou. (O `duplicar` de provas, anterior a esta regra,
   herda `ativa=p.ativa` — é o contraexemplo vivo.)
2. **O que identifica não se copia.** `PostoServico.tirvu_id` é a chave com que
   a planilha de Postos do Tirvu casa o cadastro: dois postos com o mesmo ID
   fazem a importação atualizar o posto ERRADO, em silêncio, porque ela casa
   por ID e não tem como saber qual dos dois é o certo.
3. **O que é do ORIGINAL não se copia; o que é do TRABALHO se copia.** O alvo
   de um modelo de documento (cargo/posto/pessoa) é do original — herdá-lo cria
   dois modelos disputando o mesmo destino, com `modelos-aplicaveis` devolvendo
   os dois. Já o `documentos_kit` do posto é trabalho: perdê-lo significa gente
   admitida sem assinar o termo de VT, e ninguém percebe até o desconto não
   acontecer.
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
from app.models.candidato import PostoServico  # noqa: E402
from app.models.usuario_rh import UsuarioRH  # noqa: E402
from app.models.vaga import Vaga  # noqa: E402

cliente = TestClient(app, raise_server_exceptions=False)


def main() -> int:
    falhas: list[str] = []
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    try:
        email = f"dup-{marca}@exemplo.com.br"
        db.add(UsuarioRH(nome="Teste Duplicar", email=email,
                         senha_hash=hash_senha("senha-teste-123"),
                         papel="superadmin"))
        db.commit()
        r = cliente.post("/api/rh/auth/login",
                         json={"email": email, "senha": "senha-teste-123"})
        assert r.status_code == 200, f"login falhou: {r.status_code} {r.text[:200]}"
        cab = {"Authorization": f"Bearer {r.json()['token']}"}

        # --- Posto ---------------------------------------------------------
        posto = PostoServico(nome=f"Posto Teste {marca}", tirvu_id="49",
                             documentos_kit=["termo_vt"], da_direito_creche=True,
                             ativo=True)
        db.add(posto)
        db.commit()
        db.refresh(posto)

        r = cliente.post(f"/api/rh/postos/{posto.id}/duplicar", headers=cab)
        if r.status_code != 201:
            falhas.append(f"duplicar posto: esperado 201, veio {r.status_code} "
                          f"{r.text[:200]}")
        else:
            c = r.json()
            if c["ativo"]:
                falhas.append("posto duplicado nasceu ATIVO — deveria nascer "
                              "inativo, para ser revisado antes de valer.")
            if c.get("tirvu_id"):
                falhas.append(
                    f"a cópia herdou tirvu_id={c['tirvu_id']!r} — dois postos com "
                    "o mesmo ID fazem a importação do Tirvu atualizar o posto "
                    "ERRADO, em silêncio.")
            if c.get("documentos_kit") != ["termo_vt"]:
                falhas.append(
                    f"a cópia perdeu o kit de documentos ({c.get('documentos_kit')!r}) "
                    "— posto sem kit significa gente admitida sem assinar o "
                    "termo de VT.")
            if not c.get("da_direito_creche"):
                falhas.append("a cópia perdeu o direito a creche do posto.")

            # Nome é único: duplicar de novo não pode estourar.
            r2 = cliente.post(f"/api/rh/postos/{posto.id}/duplicar", headers=cab)
            if r2.status_code != 201:
                falhas.append(
                    f"segunda cópia do posto falhou ({r2.status_code}) — o nome é "
                    "UNIQUE e o sufixo incremental deveria resolver.")

        # --- Vaga ----------------------------------------------------------
        vaga = Vaga(titulo=f"Vaga Teste {marca}", descricao="d",
                    cargo="Vigia", regiao="DF", ativa=True)
        db.add(vaga)
        db.commit()
        db.refresh(vaga)

        r = cliente.post(f"/api/rh/vagas/{vaga.id}/duplicar", headers=cab)
        if r.status_code != 201:
            falhas.append(f"duplicar vaga: esperado 201, veio {r.status_code}")
        else:
            c = r.json()
            if c["ativa"]:
                falhas.append(
                    "vaga duplicada nasceu ATIVA — passaria a receber "
                    "candidatura antes de alguém revisar os requisitos.")
            if c.get("cargo") != "Vigia":
                falhas.append("a cópia da vaga perdeu o cargo.")

        # --- Modelo de documento -------------------------------------------
        r = cliente.post("/api/rh/modelos-documento", headers=cab, json={
            "titulo": f"Modelo Teste {marca}", "corpo": "Olá {{nome}}",
            "escopo": "cargo", "cargo_alvo": "Vigia", "exige_assinatura": True})
        if r.status_code != 201:
            falhas.append(f"não criou modelo base: {r.status_code} {r.text[:200]}")
        else:
            mid = r.json()["id"]
            r = cliente.post(f"/api/rh/modelos-documento/{mid}/duplicar", headers=cab)
            if r.status_code != 201:
                falhas.append(f"duplicar modelo: veio {r.status_code}")
            else:
                c = r.json()
                if c.get("cargo_alvo"):
                    falhas.append(
                        f"a cópia herdou o alvo (cargo_alvo={c['cargo_alvo']!r}) — "
                        "dois modelos disputariam o mesmo destino e "
                        "`modelos-aplicaveis` devolveria os dois.")
                if c.get("corpo") != "Olá {{nome}}":
                    falhas.append("a cópia do modelo perdeu o corpo — que é "
                                  "justamente o trabalho que duplicar poupa.")
                if not c.get("exige_assinatura"):
                    falhas.append("a cópia perdeu `exige_assinatura`.")

        # --- Minutário ------------------------------------------------------
        r = cliente.post("/api/rh/minutario/modelos", headers=cab, json={
            "titulo": f"Msg Teste {marca}", "meio": "whatsapp",
            "corpo_base": "oi {{nome}}"})
        if r.status_code != 201:
            falhas.append(f"não criou modelo de mensagem: {r.status_code}")
        else:
            nid = r.json()["id"]
            r = cliente.post(f"/api/rh/minutario/modelos/{nid}/duplicar", headers=cab)
            if r.status_code != 201:
                falhas.append(f"duplicar minutário: veio {r.status_code}")
            elif r.json().get("ativo"):
                falhas.append("modelo de mensagem duplicado nasceu ATIVO — "
                              "apareceria para quem vai disparar antes da revisão.")
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — duplicar em posto, vaga, modelo e minutário: a cópia nasce sem\n"
          "     valer, sem o ID do Tirvu e sem o alvo do original.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
