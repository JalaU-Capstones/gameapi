from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gameapi.core.config import settings


class PostgresDatabase:
    engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    async def connect(cls) -> None:
        if cls.engine is not None:
            return

        cls.engine = create_async_engine(
            settings.postgres.uri,
            echo=settings.app.env == "development",
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        cls._session_factory = async_sessionmaker(cls.engine, expire_on_commit=False)

    @classmethod
    async def disconnect(cls) -> None:
        if cls.engine is not None:
            await cls.engine.dispose()
        cls.engine = None
        cls._session_factory = None

    @classmethod
    def get_engine(cls) -> AsyncEngine:
        if cls.engine is None:
            raise RuntimeError("PostgreSQL is not connected. Call connect() first.")
        return cls.engine

    @classmethod
    def session_factory(cls) -> async_sessionmaker[AsyncSession]:
        if cls._session_factory is None:
            raise RuntimeError("PostgreSQL is not connected. Call connect() first.")
        return cls._session_factory


def get_engine() -> AsyncEngine:
    return PostgresDatabase.get_engine()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return PostgresDatabase.session_factory()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
