from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion_service.settings import Settings, get_settings


async def init_engine(settings: Settings) -> None:
    DatabaseSessionManager.init(settings.database_url)


async def dispose_engine() -> None:
    await DatabaseSessionManager.dispose()


async def _session_dep() -> AsyncIterator[AsyncSession]:
    async with DatabaseSessionManager.session() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(_session_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
