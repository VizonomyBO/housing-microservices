"""Database session management for Lambda functions."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Database configuration from environment
DATABASE_HOST = os.environ.get("DATABASE_HOST", "localhost")
DATABASE_PORT = os.environ.get("DATABASE_PORT", "5432")
DATABASE_NAME = os.environ.get("DATABASE_NAME", "housing")
DATABASE_USER = os.environ.get("DATABASE_USER", "vizonomy_user")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")


def get_database_url() -> str:
    """Build the async PostgreSQL connection URL."""
    return (
        f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}"
        f"@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    )


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """
    Async context manager for database sessions.

    Creates a fresh engine per invocation to avoid event loop issues in Lambda.

    Usage:
        async with get_async_session() as session:
            # Use session with shared_data_layer repositories
            repo = DocumentRepository(session)
            doc = await repo.get_by_id(document_id)
    """
    # Create fresh engine per invocation - avoids event loop issues in Lambda
    engine = create_async_engine(
        get_database_url(),
        echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
        pool_size=1,
        max_overflow=0,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()
