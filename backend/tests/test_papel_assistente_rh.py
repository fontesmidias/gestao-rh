"""O papel `assistente_rh` (MCP com pessoas do RH) — o que ele NUNCA pode.

Nasceu em 19/08/2026, quando o uso do MCP mudou: deixou de ser a Claude do Bruno
lendo currículos e passou a ser a **equipe do RH no Claude Coworking, executando
tarefas por prompt**. O papel `automacao` é estreito de propósito (4 permissões
de diagnóstico) e alargá-lo desfaria a razão de ele existir — então este nasceu
ao lado, mais largo.

Este teste existe porque a proteção é uma LISTA, e lista alarga sozinha: amanhã
alguém precisa que o assistente faça mais uma coisa, acrescenta a chave, e nada
reprova. O papel deixaria de ser "o dia a dia do RH" e viraria um administrador
— em silêncio, porque tudo continua funcionando.

**O critério, quando bater a dúvida:** o ato é REVERSÍVEL e do dia a dia? Se
muda vínculo de alguém, decide dinheiro, configura o sistema para todo mundo ou
assina documento, não pertence aqui.

As quatro famílias que ficam de fora, e por quê:

1. **Irreversível** — efetivar, desligar, reverter e trocar matrícula mudam o
   VÍNCULO de uma pessoa. Um prompt mal interpretado não pode fazer isso.
2. **Dinheiro** — `creche:decidir` decide reembolso que entra em folha;
   `desempenho:homologar` fecha avaliação que vira decisão de carreira.
3. **Base inteira e trilha** — `dados:exportar_base` são 1.171 CPFs num arquivo;
   e quem é auditado não lê a própria auditoria.
4. **Assinatura** — assinar é ato de vontade de uma pessoa identificada (Lei
   14.063/2020). Assinar por prompt faria o manifesto descrever um ato que não
   aconteceu como ele afirma (a regra da v2.56).

⚠️ Se uma asserção daqui falhar depois de você acrescentar uma permissão, a
pergunta não é *"como faço o teste passar?"* — é *"este ato é reversível e do dia
a dia?"*.

Roda no bloco stdlib do CI: não importa a app, só o catálogo.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://a:b@localhost/c")

from app.services.permissoes import (PAPEIS_POR_CHAVE,  # noqa: E402
                                     permissoes_padrao, pode)

CHAVE = "assistente_rh"
falhas = []


def conferir(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


print("1. o papel existe e não é superadmin")
papel = PAPEIS_POR_CHAVE.get(CHAVE)
conferir(papel is not None, "o papel está no catálogo")
if papel is None:
    print("test_papel_assistente_rh: FALHOU — papel ausente")
    sys.exit(1)
# `tudo=True` ignora a checagem inteira: seria a chave da casa num token que
# vive no computador de alguém.
conferir(getattr(papel, "tudo", False) is False, "não ignora a checagem de permissão")

CONCEDIDAS = permissoes_padrao(CHAVE)

print("2. NUNCA muda o vínculo de alguém (irreversível)")
for perm in ("colaboradores:efetivar", "colaboradores:desligar",
             "colaboradores:reverter", "colaboradores:matricula"):
    conferir(not pode(CHAVE, CONCEDIDAS, perm), f"não pode {perm}")

print("3. NUNCA decide dinheiro nem fecha avaliação")
for perm in ("creche:decidir", "desempenho:homologar"):
    conferir(not pode(CHAVE, CONCEDIDAS, perm), f"não pode {perm}")

print("4. NUNCA puxa a base inteira nem lê a própria trilha")
for perm in ("dados:exportar_base", "dados:arquivo_lote", "dados:expurgar",
             "dados:auditoria", "dados:logs"):
    conferir(not pode(CHAVE, CONCEDIDAS, perm), f"não pode {perm}")

print("5. NUNCA configura o sistema nem cria usuário")
for perm in ("config:escrever", "config:usuarios", "recepcao:configurar"):
    conferir(not pode(CHAVE, CONCEDIDAS, perm), f"não pode {perm}")

print("6. NUNCA assina — assinatura é ato de vontade de uma pessoa")
conferir(not pode(CHAVE, CONCEDIDAS, "documentos:assinar"),
         "não pode documentos:assinar")

print("7. o dia a dia FUNCIONA (senão o papel não serve para nada)")
for perm in ("admissao:ler", "admissao:escrever", "admissao:revisar_documento",
             "selecao:escrever", "selecao:entrevistar", "creche:ler"):
    conferir(pode(CHAVE, CONCEDIDAS, perm), f"pode {perm}")

print("8. é mais largo que `automacao` e mais estreito que `rh`")
# Sem esta asserção, o papel poderia empatar com o `rh` sem ninguém notar — e aí
# ele deixaria de ser uma decisão para virar um apelido.
n_auto = len(permissoes_padrao("automacao"))
n_este = len(CONCEDIDAS)
n_rh = len(permissoes_padrao("rh"))
conferir(n_auto < n_este < n_rh,
         f"automacao({n_auto}) < assistente_rh({n_este}) < rh({n_rh})")

print()
if falhas:
    print(f"test_papel_assistente_rh: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("test_papel_assistente_rh: OK")
