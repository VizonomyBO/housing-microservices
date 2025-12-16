"""
One-off graph refresh for prod: recompute materialized views so graph_hot_entities is populated.

Usage:
  env_file=$(scripts/use_env.sh prod); set -a && source "$env_file" && set +a
  uv run python scripts/refresh_prod_graph.py

This runs in-place against DATABASE_URL from the current environment.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared_data_layer.db.maintenance import (
    refresh_graph_edge_evidence_rollup,
    refresh_graph_hot_entities,
)


@asynccontextmanager
async def session_scope(database_url: str):
    engine = create_async_engine(database_url, echo=False)
    async_session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()
        await engine.dispose()


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL must be set")

    async with session_scope(database_url) as session:
        # Refresh rollups and hot entities; assumes underlying graph tables already populated.
        await refresh_graph_edge_evidence_rollup(session, concurrently=False)
        await refresh_graph_hot_entities(session, concurrently=False)
        await session.commit()
        print("Graph rollups refreshed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
