from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.db import Base

# Importa todos os models para que o autogenerate enxergue o metadata completo.
import app.models.assinatura  # noqa: F401
import app.models.beneficio  # noqa: F401
import app.models.candidato  # noqa: F401
import app.models.configuracao  # noqa: F401
import app.models.desempenho  # noqa: F401
import app.models.desenvolvimento  # noqa: F401
import app.models.documento  # noqa: F401
import app.models.evento  # noqa: F401
import app.models.ficha  # noqa: F401
import app.models.lixeira  # noqa: F401
import app.models.modelo_documento  # noqa: F401
import app.models.talento  # noqa: F401
import app.models.teste  # noqa: F401
import app.models.usuario_rh  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # transaction_per_migration: cada revisão commita sozinha. Necessário
        # para migrations que ADICIONAM um valor de enum e o USAM logo depois
        # (Postgres proíbe usar o valor novo na MESMA transação do ADD VALUE);
        # com cada migration numa transação própria, o ADD da revisão N commita
        # antes de a revisão N+1 usar o valor. Também deixa cada migration
        # atômica de forma independente.
        context.configure(connection=connection, target_metadata=target_metadata,
                          transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
