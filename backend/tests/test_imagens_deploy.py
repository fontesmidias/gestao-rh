"""As imagens de base são puxáveis SEM login, e os dois composes concordam.

Defeito de campo em 2026-09-22: o CI reprovou em **todo commit**, no passo
"Sobe a stack completa", com

    pull access denied for minio/minio, repository does not exist
    or may require 'docker login'

O Docker Hub passou a recusar o pull anônimo de `minio/minio`. Três coisas
tornam esse defeito caro:

1. **Falha ANTES de qualquer teste rodar** — o job morre em 8s, então a
   mensagem não fala nada sobre o que se estava mexendo, e a leitura óbvia é
   "quebrei alguma coisa". Custou um CI inteiro para descobrir que era
   infraestrutura externa.
2. **O CLAUDE.md já mandava usar `quay.io/minio/minio`** nos containers
   efêmeros de teste — os ARQUIVOS DE DEPLOY é que tinham ficado para trás. A
   instrução certa existia e não alcançava o lugar que quebrou.
3. **São DOIS arquivos** (`docker-compose.base.yml` e `portainer-stack.yml`, o
   que sobe na VPS). Corrigir um só deixa o outro quebrado, e o Portainer não
   recebe o arquivo do repo sozinho — é a armadilha da v2.66/v3.15.1, que já
   cobrou quatro vezes.

O que este teste tranca:

- **Nenhum serviço usa imagem de registry que exige login.** A lista é de
  repositórios OFICIAIS conhecidos por recusar pull anônimo; qualquer um deles
  reprova, nomeando o arquivo e a linha.
- **Os dois composes usam a MESMA imagem para o mesmo serviço.** Divergir faz o
  local e a produção rodarem versões diferentes — defeito que só aparece em
  produção, que é onde não se quer descobrir.

stdlib pura (lê arquivos), roda no CI.

Rode: PYTHONPATH=. .venv/Scripts/python.exe tests/test_imagens_deploy.py
"""

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
BASE = RAIZ / "deploy" / "docker-compose.base.yml"
STACK = RAIZ / "deploy" / "portainer-stack.yml"

falhas = []

# Repositórios do Docker Hub que passaram a exigir autenticação. Não é uma
# lista de "imagens ruins": é a lista do que JÁ quebrou aqui, com o registry
# que funciona ao lado. Acrescentar uma entrada é o conserto de um incidente.
EXIGEM_LOGIN = {
    "minio/minio": "quay.io/minio/minio",
}


def _imagens(texto: str) -> list[tuple[int, str, str]]:
    """(linha, serviço, imagem) de cada `image:` do compose.

    Afirma sobre a DECLARAÇÃO, nunca sobre o texto cru: `minio/minio` aparece
    também nos COMENTÁRIOS que explicam por que ele não está mais lá, e um
    teste que casa com o comentário reprova a documentação do próprio conserto
    (v2.71/v3.15).
    """
    saida = []
    servico = "?"
    for n, linha in enumerate(texto.split("\n"), 1):
        if re.match(r"^  [a-z0-9_-]+:\s*$", linha):
            servico = linha.strip().rstrip(":")
        m = re.match(r"^\s+image:\s*(\S+)", linha)
        if m:
            saida.append((n, servico, m.group(1)))
    return saida


def teste_nenhuma_imagem_exige_login():
    for arq in (BASE, STACK):
        for n, servico, imagem in _imagens(arq.read_text(encoding="utf-8")):
            # `ghcr.io/...` e afins não entram: o repo tem credencial para eles.
            sem_tag = imagem.split(":")[0]
            if sem_tag in EXIGEM_LOGIN:
                falhas.append(
                    f"{arq.name}:{n} (serviço `{servico}`) usa `{imagem}`, que o "
                    f"Docker Hub recusa sem login — o CI morre em 'Sobe a stack "
                    f"completa', antes de qualquer teste. Use "
                    f"`{EXIGEM_LOGIN[sem_tag]}`.")


def teste_os_dois_composes_concordam():
    """Mesmo serviço, mesma imagem nos dois arquivos.

    Só compara os serviços que existem NOS DOIS: o `portainer-stack.yml` tem
    serviços a mais (nginx, console do MinIO), e exigir simetria total
    reprovaria diferença legítima — teste que acusa código correto ensina a
    equipe a ignorar o teste (v2.88).
    """
    de_base = {s: i for _, s, i in _imagens(BASE.read_text(encoding="utf-8"))}
    de_stack = {s: i for _, s, i in _imagens(STACK.read_text(encoding="utf-8"))}
    for servico in sorted(set(de_base) & set(de_stack)):
        a, b = de_base[servico], de_stack[servico]
        # As imagens da aplicação divergem DE PROPÓSITO: a base constrói do
        # código-fonte (`build:`) e a stack aponta para a publicada no GHCR.
        if "ghcr.io" in a or "ghcr.io" in b:
            continue
        if a != b:
            falhas.append(
                f"o serviço `{servico}` usa `{a}` em {BASE.name} e `{b}` em "
                f"{STACK.name} — local e produção rodariam versões diferentes, "
                f"e a diferença só apareceria na VPS.")


for t in (teste_nenhuma_imagem_exige_login, teste_os_dois_composes_concordam):
    t()


def _reportar(itens: list[str]) -> None:
    """Emoji em mensagem de falha quebra o teste no console do Windows
    (cp1252): o script morre ANTES de mostrar a causa (v3.15)."""
    print("FALHOU:")
    for item in itens:
        try:
            print(f"  - {item}")
        except UnicodeEncodeError:
            print("  - " + item.encode("ascii", "replace").decode("ascii"))


if falhas:
    _reportar(falhas)
    sys.exit(1)
print("OK - nenhuma imagem exige login, e os dois composes concordam.")
