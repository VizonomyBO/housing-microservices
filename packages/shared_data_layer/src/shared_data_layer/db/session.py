from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseSessionManager:
    _engine: Optional[AsyncEngine] = None
    _session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    @classmethod
    def init(
        cls,
        database_url: str,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
    ) -> None:
        cls._engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        cls._session_factory = async_sessionmaker(
            bind=cls._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncIterator[AsyncSession]:
        if cls._session_factory is None:
            raise Exception("DatabaseSessionManager is not initialized")

        async with cls._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    @classmethod
    async def dispose(cls) -> None:
        if cls._engine:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None

    @classmethod
    def override_engine(cls, engine: AsyncEngine) -> None:
        cls._engine = engine
        cls._session_factory = async_sessionmaker(
            bind=cls._engine,
            expire_on_commit=False,
            autoflush=False,
        )
