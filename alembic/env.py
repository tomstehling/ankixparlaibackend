import asyncio
from logging.config import fileConfig

# This is the crucial part for loading the .env file
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- YOUR MODELS ---
# It's better practice to import them explicitly than with a wildcard
from database.models import *

# This is the target metadata for 'autogenerate' support
target_metadata = Base.metadata
# --------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode for an async engine.
    This version is type-safe and correctly handles connect_args.
    """
    import os
    import uuid

    db_url = os.getenv("SUPABASE_DATABASE_URL_IPV4")
    if not db_url:
        raise ValueError("MIGRATION_DATABASE_URL environment variable is not set.")

    # Define our non-string connection arguments separately

    # Pass the connect_args as a keyword argument to the function.
    # This is the clean, type-safe way to do it.
    connectable = create_async_engine(
        url=db_url,
        connect_args={
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connection.close()  # It's good practice to close the connection explicitly
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Run the async online migration function
    asyncio.run(run_migrations_online())
