from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

_WORKFLOW_MOVE_SUBTREE_SQL = text(
    "SELECT workflow_nodes_move_subtree(:graph_id, :src, :dst)"
)


async def workflow_nodes_move_subtree(
    session: AsyncSession,
    *,
    graph_id: UUID,
    source_path: str,
    target_parent_path: str,
) -> None:
    """Call the workflow_nodes_move_subtree stored procedure asynchronously."""

    await session.execute(
        _WORKFLOW_MOVE_SUBTREE_SQL,
        {"graph_id": graph_id, "src": source_path, "dst": target_parent_path},
    )


def workflow_nodes_move_subtree_sync(
    connection: Connection,
    *,
    graph_id: UUID,
    source_path: str,
    target_parent_path: str,
) -> None:
    """Synchronous helper for moving workflow subtrees via stored procedure."""

    connection.execute(
        _WORKFLOW_MOVE_SUBTREE_SQL,
        {"graph_id": graph_id, "src": source_path, "dst": target_parent_path},
    )
