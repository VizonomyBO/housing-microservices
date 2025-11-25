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
    
    # Run Alembic Migrations
    # We need to run this synchronously
    import os
    from alembic.config import Config
    from alembic import command
    
    # Find alembic.ini relative to this file
    # This file is in src/shared_data_layer/testing/conftest.py
    # alembic.ini is in src/shared_data_layer/migrations/alembic.ini
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
    # We need to point to the alembic.ini file. 
    # Let's try to find it robustly.
    alembic_ini_path = os.path.join(current_dir, "../migrations/alembic.ini")
    alembic_ini_path = os.path.abspath(alembic_ini_path)
    
    # Also need to set script_location to be absolute or relative to alembic.ini
    # In alembic.ini it is likely `script_location = .` or `script_location = shared_data_layer/migrations`
    # Let's check alembic.ini content if this fails, but usually setting the config object works.
    
    alembic_cfg = Config(alembic_ini_path)
    
    # Set the env var so Settings() doesn't explode when env.py imports it
    os.environ["DATABASE_URL"] = database_url
    
    # Override the database URL in alembic config as well
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    # We also need to set script_location explicitly if the ini uses a relative path that assumes CWD
    script_location = os.path.join(os.path.dirname(alembic_ini_path))
    alembic_cfg.set_main_option("script_location", script_location)

    # Run upgrade
    # Since env.py is async, we can't just call command.upgrade(cfg, "head") if it tries to use a sync engine?
    # Wait, our env.py is designed for async. It uses `connectable = context.config.attributes.get("connection", None)`
    # or creates an async engine.
    # If we call command.upgrade, it runs env.py.
    # If env.py does `run_migrations_online`, it creates an engine.
    # We should probably check env.py.
    
    # Actually, simpler approach:
    # Just run the migrations using the CLI command via subprocess if programmatic is hard due to async loop issues?
    # No, let's try programmatic. But we need to be careful about the loop.
    # command.upgrade is a sync function. It calls env.py.
    # If env.py does `asyncio.run`, it might conflict with the existing loop?
    # Our env.py likely has `if asyncio.get_event_loop().is_running(): ...` checks?
    # Let's assume standard async env.py pattern.
    
    # To avoid loop conflicts, we can run it in a separate thread or process, OR
    # since we are in `async def engine`, we have a running loop.
    # If env.py calls `asyncio.run()`, it will fail.
    
    # Let's look at env.py first to be safe.
    # But for now, let's try to just run the SQL directly for the specific missing things?
    # No, that's tech debt.
    
    # Alternative: Use `conn.run_sync` to run alembic?
    # `await conn.run_sync(run_alembic_upgrade, alembic_cfg)`
    
    def run_upgrade(connection, cfg):
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    async with engine.begin() as conn:
        await conn.run_sync(run_upgrade, alembic_cfg)
        
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
