import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import all ORM models so Alembic autogenerate picks them up
from src.apps.incidents.adapters.orm import IncidentModel, NodeStatsSnapshotModel  # noqa: F401
from src.apps.nodes.adapters.orm import MutedNodeModel  # noqa: F401
from src.infrastructure.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    import os

    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv("DATABASE_URL", "")


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = get_url()
    connectable = create_async_engine(url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
