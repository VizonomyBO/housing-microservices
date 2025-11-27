from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

_REFRESH_BASE_SQL = text("SELECT refresh_base_documents_by_country(:country_code)")
_REFRESH_GRAPH_SQL = text("SELECT refresh_graph_materializations(:concurrently)")


async def refresh_base_documents_cache(
    session: AsyncSession, country_code: Optional[str] = None
) -> None:
    await session.execute(_REFRESH_BASE_SQL, {"country_code": country_code})


def refresh_base_documents_cache_sync(
    connection: Connection, country_code: Optional[str] = None
) -> None:
    connection.execute(_REFRESH_BASE_SQL, {"country_code": country_code})


async def refresh_all_base_documents_cache(session: AsyncSession) -> None:
    """Rebuild the cache for every country partition."""

    await refresh_base_documents_cache(session, None)


async def refresh_base_documents_cache_for_country(
    session: AsyncSession, country_code: str
) -> None:
    """Refresh a single country partition."""

    await refresh_base_documents_cache(session, country_code)


def refresh_all_base_documents_cache_sync(connection: Connection) -> None:
    """Synchronous helper for refreshing every country partition."""

    refresh_base_documents_cache_sync(connection, None)


def refresh_base_documents_cache_for_country_sync(
    connection: Connection, country_code: str
) -> None:
    """Synchronous helper for refreshing a specific country partition."""

    refresh_base_documents_cache_sync(connection, country_code)


async def refresh_graph_materializations(
    session: AsyncSession, concurrently: bool = False
) -> None:
    await session.execute(_REFRESH_GRAPH_SQL, {"concurrently": concurrently})


def refresh_graph_materializations_sync(
    connection: Connection, concurrently: bool = False
) -> None:
    connection.execute(_REFRESH_GRAPH_SQL, {"concurrently": concurrently})
