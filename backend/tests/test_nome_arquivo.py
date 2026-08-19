"""Nome dos arquivos baixados (`services/nome_arquivo.py`, v3.04).

Padrão cravado pelo Bruno (18/08/2026): `matrícula - nome - documento`, caixa
alta, sem caractere especial, matrícula em 6 posições. Vale para os módulos
existentes e os vindouros.

O que este teste protege:

1. **Nada de acento nem aspas no header.** `Content-Disposition` só carrega
   ASCII com segurança, e uma aspa dupla no nome quebra a delimitação do
   cabeçalho — o arquivo chegaria com nome truncado ou o header inválido.
2. **Parte vazia não deixa separador solto.** Em admissão a matrícula quase
   sempre não existe; ` - MARIA - FICHA.pdf` tem um hífen órfão na frente, que
   todo mundo lê como erro.
3. **Nunca devolve nome vazio.** Arquivo sem nome não pode ser salvo.
4. **Nome reservado do Windows não passa cru** (`CON.pdf` não se cria).

Stdlib pura — o serviço é de texto.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://a:b@localhost/c")

from app.services.nome_arquivo import limpar, montar  # noqa: E402

falhas = []


def conferir(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


print("1. o padrão do Bruno, na ordem certa")
conferir(montar("3035", "Maria de Fátima Souza", "Ficha de admissão")
         == "003035 - MARIA DE FATIMA SOUZA - FICHA DE ADMISSAO.pdf",
         "matrícula (6 díg) - nome - documento, caixa alta e sem acento")
conferir(montar("3035", "Maria", "Planilha", "xlsx").endswith(".xlsx"),
         "a extensão é de quem chama")

print("2. o header HTTP não pode quebrar")
nome = montar("12", 'Maria/José: a "melhor"', "Relatório <2026>")
conferir('"' not in nome, "sem aspas duplas (quebrariam o Content-Disposition)")
conferir(all(ord(c) < 128 for c in nome), "só ASCII")
for proibido in "\\/:*?<>|":
    conferir(proibido not in nome, f"sem o caractere {proibido!r} (proibido no Windows)")

print("3. hífen dentro do nome não vira separador falso")
# `ANA-MARIA` viraria "ANA" e "MARIA" na leitura de quem separa por " - "
conferir("ANA MARIA" in montar("12", "Ana-Maria", "Doc"),
         "hífen no nome da pessoa vira espaço")

print("4. parte vazia é OMITIDA junto com o separador")
sem_matricula = montar(None, "Ana Paula", "Dossiê")
conferir(sem_matricula == "ANA PAULA - DOSSIE.pdf",
         "sem matrícula (o caso normal em admissão) não sobra hífen na frente")
conferir(not sem_matricula.startswith(" ") and not sem_matricula.startswith("-"),
         "e o nome não começa com separador")

print("5. nunca devolve nome vazio nem reservado do Windows")
conferir(montar(None, None, None) == "DOCUMENTO.pdf",
         "sem nenhuma parte, ainda há um nome")
conferir(montar(None, None, "CON") != "CON.pdf",
         "nome reservado do Windows não passa cru")

print("6. `limpar` sozinho")
conferir(limpar("  josé   d'ávila  ") == "JOSE D'AVILA", "normaliza espaços e acento")
conferir(limpar(None) == "" and limpar("") == "", "nulo/vazio devolve vazio")

print()
if falhas:
    print(f"test_nome_arquivo: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("test_nome_arquivo: OK")
