from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Config


def create_engine(config: Config) -> AsyncEngine:
    return create_async_engine(config.database_url, echo=False)
