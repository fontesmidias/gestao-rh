#!/bin/sh
set -e

# Migra o schema ANTES de subir a aplicação: atualizações nunca perdem dados,
# apenas evoluem as tabelas (alembic upgrade é incremental e transacional).
# Só a API migra (evita corrida com o worker, que sobe em paralelo).
#
# A FALHA DA MIGRATION NÃO DERRUBA A API (decisão do Bruno, 2026-08-06).
# Antes, o `set -e` abortava o script e o `exec uvicorn` nunca era alcançado:
# uma migration com defeito tirava o sistema INTEIRO do ar, e nenhum restart
# resolvia, porque a falha se repetia a cada subida. Foi o que aconteceu na
# manhã de 2026-08-06 — do lado de quem usa, "não loga, o back não fala com o
# banco"; na verdade não havia back nenhum.
#
# Schema velho com o sistema no ar é melhor que tela morta: o login continua
# funcionando, dá para diagnosticar com calma e o `/api/health` DENUNCIA o
# atraso (`migracoes.em_dia: false`) — que é o que aquele campo sempre se
# propôs a fazer e não conseguia, porque sem API não há /health para consultar.
case "$1" in
  uvicorn)
    echo ">> alembic upgrade head"
    if alembic upgrade head; then
      echo ">> migrations em dia"
    else
      echo ">> FALHA NA MIGRATION — a API sobe assim mesmo, com o schema" >&2
      echo ">> ANTERIOR. Confira /api/health (migracoes.em_dia) e o log" >&2
      echo ">> acima para o erro do alembic." >&2
    fi
    ;;
esac

exec "$@"
