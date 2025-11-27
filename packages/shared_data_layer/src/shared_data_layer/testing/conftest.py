import asyncio
from typing import AsyncGenerator, Generator

import asyncpg
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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

    async def _wait_for_database_ready(
        retries: int = 30,
        delay_seconds: float = 0.5,
    ) -> None:
        last_exc: Exception | None = None
        for _ in range(retries):
            try:
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                return
            except (
                OperationalError,
                asyncpg.exceptions.CannotConnectNowError,
                ConnectionError,
                OSError,
            ) as exc:
                last_exc = exc
                await asyncio.sleep(delay_seconds)
        if last_exc is not None:
            raise last_exc

    @event.listens_for(engine.sync_engine, "connect")
    def _register_char_codec(dbapi_connection, connection_record):
        await_ = getattr(dbapi_connection, "await_", None)
        if await_ is None:
            return

        async def _setup():
            try:
                await dbapi_connection._connection.set_builtin_type_codec(  # type: ignore[attr-defined]
                    "char",
                    codec_name="text",
                    format="text",
                )
            except Exception:
                return

        await_(_setup())

    # Run Alembic migrations synchronously so the test DB matches the latest schema
    import os

    from alembic import command
    from alembic.config import Config

    current_dir = os.path.dirname(os.path.abspath(__file__))
    alembic_ini_path = os.path.abspath(
        os.path.join(current_dir, "../migrations/alembic.ini")
    )

    alembic_cfg = Config(alembic_ini_path)

    os.environ["DATABASE_URL"] = database_url

    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    script_location = os.path.dirname(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", script_location)

    # Run upgrade via the SQLAlchemy connection to honor env.py's async logic

    def run_upgrade(connection, cfg):
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    await _wait_for_database_ready()

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
        await session.begin()
        yield session
        await session.rollback()
