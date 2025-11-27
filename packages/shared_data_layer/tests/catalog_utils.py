from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PartitionCatalogSnapshot:
    table_name: str
    strategy: str | None
    partitions: Set[str]
    default_partition: str | None


async def fetch_partition_catalog(
    session: AsyncSession, table_name: str
) -> PartitionCatalogSnapshot:
    """Return partitioning metadata for a parent table."""

    strategy_row = await session.execute(
        text(
            """
            SELECT partstrat::text AS strategy
            FROM pg_partitioned_table pt
            JOIN pg_class c ON pt.partrelid = c.oid
            WHERE c.relname = :table
            """
        ),
        {"table": table_name},
    )
    strategy = strategy_row.scalar_one_or_none()

    partition_rows = await session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class parent ON parent.oid = i.inhparent
            WHERE parent.relname = :table
            """
        ),
        {"table": table_name},
    )
    partitions = {row[0] for row in partition_rows}

    default_partition = None
    if strategy:
        default_row = await session.execute(
            text(
                """
                SELECT child.relname
                FROM pg_partitioned_table pt
                JOIN pg_class parent ON parent.oid = pt.partrelid
                JOIN pg_class child ON child.oid = pt.partdefid
                WHERE parent.relname = :table
                """
            ),
            {"table": table_name},
        )
        default_partition = default_row.scalar_one_or_none()

    return PartitionCatalogSnapshot(
        table_name=table_name,
        strategy=strategy,
        partitions=partitions,
        default_partition=default_partition,
    )


async def fetch_index_catalog(session: AsyncSession, table_name: str) -> Dict[str, str]:
    """Return a map of index names to their definitions for a table."""

    rows = await session.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = :table
            """
        ),
        {"table": table_name},
    )
    return {row.indexname: row.indexdef for row in rows}
