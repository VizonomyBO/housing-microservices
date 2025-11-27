from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

_REFRESH_BASE_SQL = text("SELECT refresh_base_documents_by_country(:country_code)")
_REFRESH_GRAPH_SQL = text("SELECT refresh_graph_materializations(:concurrently)")
_REFRESH_GRAPH_COMMUNITIES_SQL = text(
    "SELECT refresh_graph_communities(:country_code, :algo_version, :community_id)"
)
_REFRESH_ACTIVE_CHUNKS_SQL = {
    False: text("REFRESH MATERIALIZED VIEW active_chunks"),
    True: text("REFRESH MATERIALIZED VIEW CONCURRENTLY active_chunks"),
}
_REFRESH_GRAPH_EDGE_EVIDENCE_SQL = {
    False: text("REFRESH MATERIALIZED VIEW graph_edge_evidence_rollup"),
    True: text("REFRESH MATERIALIZED VIEW CONCURRENTLY graph_edge_evidence_rollup"),
}
_REFRESH_GRAPH_HOT_ENTITIES_SQL = {
    False: text("REFRESH MATERIALIZED VIEW graph_hot_entities"),
    True: text("REFRESH MATERIALIZED VIEW CONCURRENTLY graph_hot_entities"),
}


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


async def refresh_graph_community_rollups(
    session: AsyncSession,
    *,
    country_code: Optional[str] = None,
    algo_version: Optional[str] = None,
    community_id: Optional[UUID] = None,
) -> None:
    """Recompute community metrics/rosters for the requested scope."""

    await session.execute(
        _REFRESH_GRAPH_COMMUNITIES_SQL,
        {
            "country_code": country_code,
            "algo_version": algo_version,
            "community_id": community_id,
        },
    )


def refresh_graph_community_rollups_sync(
    connection: Connection,
    *,
    country_code: Optional[str] = None,
    algo_version: Optional[str] = None,
    community_id: Optional[UUID] = None,
) -> None:
    """Synchronous helper for recomputing community rollups."""

    connection.execute(
        _REFRESH_GRAPH_COMMUNITIES_SQL,
        {
            "country_code": country_code,
            "algo_version": algo_version,
            "community_id": community_id,
        },
    )


async def refresh_active_chunks_view(
    session: AsyncSession, concurrently: bool = False
) -> None:
    """Refresh the materialized `active_chunks` snapshot after document updates."""

    statement = _REFRESH_ACTIVE_CHUNKS_SQL[bool(concurrently)]
    await session.execute(statement)


def refresh_active_chunks_view_sync(
    connection: Connection, concurrently: bool = False
) -> None:
    """Synchronous helper for refreshing the `active_chunks` materialized view."""

    statement = _REFRESH_ACTIVE_CHUNKS_SQL[bool(concurrently)]
    connection.execute(statement)


async def refresh_graph_edge_evidence_rollup(
    session: AsyncSession, concurrently: bool = False
) -> None:
    """Refresh the graph_edge_evidence_rollup materialized view."""

    statement = _REFRESH_GRAPH_EDGE_EVIDENCE_SQL[bool(concurrently)]
    await session.execute(statement)


def refresh_graph_edge_evidence_rollup_sync(
    connection: Connection, concurrently: bool = False
) -> None:
    """Synchronous helper for refreshing graph_edge_evidence_rollup."""

    statement = _REFRESH_GRAPH_EDGE_EVIDENCE_SQL[bool(concurrently)]
    connection.execute(statement)


async def refresh_graph_hot_entities(
    session: AsyncSession, concurrently: bool = False
) -> None:
    """Refresh the graph_hot_entities materialized view."""

    statement = _REFRESH_GRAPH_HOT_ENTITIES_SQL[bool(concurrently)]
    await session.execute(statement)


def refresh_graph_hot_entities_sync(
    connection: Connection, concurrently: bool = False
) -> None:
    """Synchronous helper for refreshing graph_hot_entities."""

    statement = _REFRESH_GRAPH_HOT_ENTITIES_SQL[bool(concurrently)]
    connection.execute(statement)
