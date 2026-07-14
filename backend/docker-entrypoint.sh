#!/bin/sh
set -e

# Migra o schema ANTES de subir a aplicação: atualizações nunca perdem dados,
# apenas evoluem as tabelas (alembic upgrade é incremental e transacional).
# Só a API migra (evita corrida com o worker, que sobe em paralelo).
case "$1" in
  uvicorn)
    echo ">> alembic upgrade head"
    alembic upgrade head
    ;;
esac

exec "$@"
