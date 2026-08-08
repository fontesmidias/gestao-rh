"""A versão do sistema, num lugar só.

Existe porque o `VERSAO_DEPLOY` chumbado à mão em `api/health.py` congelou DUAS
vezes: parou na `v1.50` por vinte versões, foi anotado como mau exemplo no
docstring da função vizinha (`_revisao_esperada`) — e congelou de novo na
`v2.27`, por outras vinte e seis. O Bruno descobriu do jeito mais direto: abriu
`/api/health` depois de um deploy conferido e leu uma versão de um mês atrás.

Uma constante esquecida não avisa que está errada; ela responde com a maior
confiança do mundo. Por isso a defesa NÃO é "lembrar de atualizar": é o
`test_versao.py`, que compara este valor com o topo do `CHANGELOG.md` e reprova
no CI quando os dois divergem. Sem o teste, isto congela uma terceira vez.

Por que aqui e não derivado do CHANGELOG em tempo de execução: o contexto de
build da imagem da API é `./backend` (ver `.github/workflows/ci.yml`), e o
`CHANGELOG.md` mora na RAIZ do repositório — ele não entra na imagem. Ler o
arquivo em runtime daria `None` em produção e a versão certa só na máquina de
quem desenvolve, que é o pior dos dois mundos: parece funcionar onde não
importa.
"""

# Mantenha em sincronia com o topo do CHANGELOG.md — o `test_versao.py` cobra.
VERSAO = "2.78.0"

# Rótulo curto do que a versão entregou. Aparece ao lado do número na tela de
# Configurações; é o que faz "2.54.0" virar uma informação em vez de um número.
VERSAO_NOME = "Um botão, dois estados"


def versao_completa() -> str:
    """`v2.53.0 — Ver como se responde, antes de começar`, para exibir."""
    return f"v{VERSAO} — {VERSAO_NOME}" if VERSAO_NOME else f"v{VERSAO}"
