from alembic import context
from sqlalchemy import engine_from_config, pool

from athleteiq import models  # noqa: F401  (registers tables)
from athleteiq.config import settings
from athleteiq.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings().database_url)
target_metadata = Base.metadata


def run():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          render_as_batch=conn.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


run()
