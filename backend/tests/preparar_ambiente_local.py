"""Garante o usuário PADRÃO de testes locais (v2.85).

Pedido do Bruno (2026-08-08): *"para os testes locais, deixe um user e senha
padrão, para não perdermos mais tempo."*

O tempo perdido era sempre o mesmo: `criar_admin_inicial` só cria o admin do
`.env` quando a tabela está **vazia**. Num banco de desenvolvimento com usuários
antigos, o admin do `.env` simplesmente NÃO EXISTE — e o sintoma é um `401` que
aparece como `KeyError: 'token'` ou como "senha errada", apontando para o lugar
errado. Isso mordeu no smoke, no `test_email_templates` e nos testes de tela, em
sequência, no mesmo dia.

Este script resolve de frente: cria (ou redefine a senha de) um usuário fixo,
sempre o mesmo. Rode uma vez depois de subir a stack local e esqueça o assunto.

    docker exec -e PYTHONPATH=. <container-api> python tests/preparar_ambiente_local.py

    # ou, com o venv apontando para o banco local:
    PYTHONPATH=. .venv/Scripts/python.exe tests/preparar_ambiente_local.py

⚠️ **Só para desenvolvimento.** A senha é conhecida e está escrita aqui, num
repositório PÚBLICO. Ele recusa rodar quando `ENVIRONMENT=production` — e, ainda
assim, nunca aponte para o banco de produção.
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "segredo-de-teste")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:59000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio12345")

# O usuário padrão dos testes locais. Estes dois valores são a razão de o script
# existir: escritos UMA vez, nunca mais adivinhados.
EMAIL = "teste@exemplo.com.br"
SENHA = "senha-teste-123"
NOME = "Usuário de Teste"

if os.environ.get("ENVIRONMENT", "").lower() in {"production", "producao", "prod"}:
    print("RECUSADO: ENVIRONMENT indica produção. Este script cria um usuário com "
          "senha conhecida e é só para desenvolvimento.")
    sys.exit(1)

from sqlalchemy import select                       # noqa: E402

from app.core.db import SessionLocal                # noqa: E402
from app.core.security import hash_senha            # noqa: E402
from app.models.usuario_rh import UsuarioRH         # noqa: E402

with SessionLocal() as db:
    u = db.scalar(select(UsuarioRH).where(UsuarioRH.email == EMAIL))
    if u is None:
        db.add(UsuarioRH(nome=NOME, email=EMAIL, senha_hash=hash_senha(SENHA)))
        acao = "criado"
    else:
        # Redefine sempre: o banco local pode ter uma senha antiga, e o ponto do
        # script é que estas credenciais funcionem SEM ninguém precisar conferir.
        u.senha_hash = hash_senha(SENHA)
        u.ativo = True
        acao = "atualizado"
    db.commit()

print(f"Usuário de teste {acao}.")
print(f"  e-mail: {EMAIL}")
print(f"  senha : {SENHA}")
print()
print("Use nos testes locais:")
print(f"  RH_ADMIN_EMAIL={EMAIL} RH_ADMIN_PASSWORD={SENHA} \\")
print("    PYTHONPATH=. .venv/Scripts/python.exe tests/<teste>.py")
print()
print("Nos testes de tela (Playwright):")
print(f"  BASE_URL=http://localhost:8090 RH_EMAIL={EMAIL} RH_SENHA={SENHA} \\")
print("    npx playwright test --workers=1")
print()
print("⚠️  `--workers=1` importa: em paralelo, a suíte estoura o rate limit do")
print("    login (15/5min por IP) e as falhas PARECEM defeito de layout.")
