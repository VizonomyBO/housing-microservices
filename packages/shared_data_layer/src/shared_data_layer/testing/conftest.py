import asyncio
from typing import AsyncGenerator, Generator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from shared_data_layer.db.base import Base
from shared_data_layer.testing.containers import PostgresContainerWithVector


@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainerWithVector, None, None]:
    with PostgresContainerWithVector() as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainerWithVector) -> str:
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
async def engine(database_url: str):
    engine = create_async_engine(database_url, echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(scope="function")
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()
