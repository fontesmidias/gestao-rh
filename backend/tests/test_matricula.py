"""Matrícula automática: as DUAS faixas e a formatação de 6 dígitos (v3.03).

Decisão do Bruno (18/08/2026): a matrícula gerada pelo sistema passa a ter
**6 dígitos** (`99` + 4), para caber no padrão de nome de arquivo
`MATRÍCULA - NOME - DOCUMENTO`. **Só para as próximas** — quem já tem a antiga
(`999` + 4, 7 dígitos) fica como está: aquele número já foi para o Tirvu e para
a planilha de ponto, e trocá-lo criaria duas matrículas para a mesma pessoa nos
dois sistemas.

O que este teste protege:

1. **`999001` NÃO é da nossa faixa.** Tem 6 dígitos e começa com `99`, então a
   leitura ingênua a tomaria por `99` + `9001` — e o gerador pularia para
   `999002`, invadindo a numeração do Tirvu, onde pode haver outra pessoa. É o
   defeito mais caro possível aqui: matrícula duplicada entre dois sistemas.
2. **O gerador considera as duas faixas.** `9990007` e `990007` compartilham o
   sequencial; ignorar a legada faria a primeira matrícula nova repetir um
   número já usado.
3. **Zero-pad não quebra o casamento do ponto.** `matricula_norm` ignora zeros à
   esquerda, então formatar para exibir é seguro — é o que autoriza o padrão de
   6 dígitos no nome do arquivo sem tocar no dado gravado.
4. **Não se trunca o que é maior.** Cortar `9990001` para caber em 6 posições
   viraria OUTRO número, e o nome do arquivo deixaria de identificar a pessoa.

Stdlib pura (nem banco nem app): as funções são de texto.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os  # noqa: E402

os.environ.setdefault("SECRET_KEY", "teste")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://a:b@localhost/c")

from app.services.export_tirvu import (  # noqa: E402
    PREFIXO_MATRICULA_AUTO, PREFIXO_MATRICULA_LEGADO, matricula_automatica,
    matricula_formatada)
from app.services.import_ponto import matricula_norm  # noqa: E402

falhas = []


def conferir(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHOU'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


print("1. a faixa nova tem 6 dígitos; a legada continua reconhecida")
conferir(PREFIXO_MATRICULA_AUTO == "99", "o prefixo novo é 99")
conferir(PREFIXO_MATRICULA_LEGADO == "999", "o legado continua 999")
conferir(matricula_automatica("990001") is True, "990001 é nossa (faixa nova)")
conferir(matricula_automatica("9990001") is True, "9990001 é nossa (faixa legada)")

print("2. matrícula REAL do Tirvu não pode ser confundida com a nossa")
# ⚠️ o caso que quebraria tudo: 6 dígitos começando com 99
conferir(matricula_automatica("999001") is False,
         "999001 (6 díg, do Tirvu) NÃO é da nossa faixa")
conferir(matricula_automatica("3035") is False, "matrícula curta do Tirvu")
conferir(matricula_automatica("123456") is False, "6 dígitos comuns do Tirvu")
conferir(matricula_automatica(None) is False and matricula_automatica("") is False,
         "vazio/nulo não é matrícula automática")

print("3. formatação de 6 dígitos — para EXIBIR, sem mudar o gravado")
conferir(matricula_formatada("3035") == "003035", "3035 vira 003035")
conferir(matricula_formatada("990001") == "990001", "a nova já tem 6")
conferir(matricula_formatada("12") == "000012", "completa com zeros")
conferir(matricula_formatada(None) == "" and matricula_formatada("") == "",
         "sem matrícula devolve vazio, NÃO '000000' (que seria um número)")

print("4. o que é MAIOR que 6 dígitos não é truncado")
# truncar viraria outro número, e o nome do arquivo deixaria de identificar
conferir(matricula_formatada("9990001") == "9990001",
         "a legada de 7 dígitos sai inteira")
conferir(matricula_formatada("12345678") == "12345678",
         "matrícula longa do Tirvu sai inteira")

print("5. zero-pad NÃO quebra o casamento da planilha de ponto")
for crua in ("3035", "12", "990001", "9990001"):
    conferir(matricula_norm(matricula_formatada(crua)) == matricula_norm(crua),
             f"{crua} formatada continua casando com a original")

print()
if falhas:
    print(f"test_matricula: {len(falhas)} FALHA(S)")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)
print("test_matricula: OK")
