"""Texto longo no cadastro de talento: cabe — e, quando não cabe, a tela DIZ.

Defeito de campo (2026-08-10): o Bruno não conseguia cadastrar talento à mão. O
log mostrava `StringDataRightTruncation` numa `varchar(60)` com **106
caracteres** — "Técnico em Secretariado / Secretário Executivo; Inglês avançado
(cursando, Centro de Idiomas de Ceilândia)".

Eram DOIS defeitos, e o segundo é o pior:

1. A coluna nasceu dimensionada para o formulário PÚBLICO, onde a escolaridade
   sai de uma lista curta. No cadastro pelo RH o campo é texto livre, e o real
   não cabia. **Coluna dimensionada para o caminho de entrada mais estreito
   quebra no dia em que aparece o outro** — e este projeto tem quase sempre
   dois caminhos para o mesmo dado (público × RH, wizard × importação).
2. O erro virava **HTTP 500 em texto puro**: a tela dizia "não foi possível" e
   o RH refazia o cadastro inteiro sem saber qual campo encurtar. É a família
   do "não salva e não diz o motivo" da v1.96.

O teste afirma as duas coisas. A segunda importa mais no longo prazo: alargar
uma coluna resolve UM campo, dizer o motivo resolve todos os próximos.
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

cliente = TestClient(app, raise_server_exceptions=False)

# O texto REAL que falhou em produção. Constante conhecida do teste, não valor
# lido do sistema (a lição da v2.64): se a coluna encolher, isto reprova.
ESCOLARIDADE_REAL = ("Técnico em Secretariado / Secretário Executivo; "
                     "Inglês avançado (cursando, Centro de Idiomas de Ceilândia)")


def main() -> int:
    falhas: list[str] = []
    db = SessionLocal()
    marca = uuid.uuid4().hex[:8]
    try:
        email = f"tal-{marca}@exemplo.com.br"
        db.add(UsuarioRH(nome="Teste Talento", email=email,
                         senha_hash=hash_senha("senha-teste-123"),
                         papel="superadmin"))
        db.commit()
        r = cliente.post("/api/rh/auth/login",
                         json={"email": email, "senha": "senha-teste-123"})
        assert r.status_code == 200, f"login falhou: {r.status_code} {r.text[:200]}"
        cab = {"Authorization": f"Bearer {r.json()['token']}"}

        # 1. O caso real cadastra. 106 caracteres numa coluna que tinha 60.
        r = cliente.post("/api/rh/talentos", headers=cab, json={
            # Nome único por execução: a rota detecta homônimo por nome+telefone
            # e devolveria 409 na segunda rodada — teste que só passa em
            # banco limpo é armadilha (v2.14).
            "nome": f"Alessandra Karla {marca}",
            "email": f"ale-{marca}@exemplo.com.br",
            "telefone": "+55 61 99514-7507",
            "cargos_interesse": ["Secretariado"],
            "cidade": "Taguatinga-DF",
            "escolaridade": ESCOLARIDADE_REAL,
            "resumo": "Currículo enviado por terceiro em nome da candidata. " * 12,
            "origem": "Currículo por e-mail"})
        if r.status_code != 201:
            falhas.append(
                f"o cadastro real deveria funcionar, veio {r.status_code}: "
                f"{r.text[:220]}")
        elif (r.json().get("escolaridade") or "") != ESCOLARIDADE_REAL:
            falhas.append(
                "a escolaridade foi gravada TRUNCADA — pior que recusar: o RH "
                "acha que salvou e o dado está pela metade.")

        # 2. Excesso de verdade vira 422 NOMEANDO o campo, o limite e o tamanho.
        #    Sem isso, o RH refaz o cadastro inteiro adivinhando o que encurtar.
        r = cliente.post("/api/rh/talentos", headers=cab, json={
            "nome": f"Fulano Longo {marca}",
            "email": f"f-{marca}@exemplo.com.br",
            "cargos_interesse": ["Secretariado"],
            "escolaridade": "X" * 400})
        if r.status_code == 500:
            falhas.append(
                "texto acima do limite ainda devolve 500 — a tela não diz o "
                "motivo e o RH não tem como saber qual campo encurtar.")
        elif r.status_code != 422:
            falhas.append(f"esperado 422 para texto longo, veio {r.status_code}")
        else:
            det = (r.json() or {}).get("detail") or {}
            campos = det.get("campos") or []
            if det.get("erro") != "campo_muito_longo" or not campos:
                falhas.append(f"o 422 não diz o que estourou: {det!r}")
            elif campos[0].get("campo") != "escolaridade":
                falhas.append(f"o 422 nomeou o campo errado: {campos!r}")
            elif not campos[0].get("limite"):
                falhas.append(
                    "o 422 não diz o LIMITE — 'muito longo' sem o número deixa "
                    "o RH cortando texto no escuro.")
    finally:
        db.close()

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  •", f)
        return 1
    print("OK — o cadastro real cabe, e o que não cabe é recusado dizendo\n"
          "     qual campo, qual o limite e quanto veio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
