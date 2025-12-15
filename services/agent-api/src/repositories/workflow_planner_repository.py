"""Workflow planning repository helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from shared_data_layer.db.models.workflow import WorkflowGraph, WorkflowNode, WorkflowVersion
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


@dataclass(slots=True)
class WorkflowNodeSnapshot:
    """Workflow node metadata required to build LangGraph plans."""

    key: str
    path: str
    description: str | None
    preconditions: dict[str, Any]
    tool_hints: list[str]
    artifacts: dict[str, Any]


@dataclass(slots=True)
class WorkflowPlanSource:
    """Workflow graph projection consumed by WorkflowPlannerNode."""

    graph_id: str
    name: str
    domain: str
    version: str | None
    country_code: str | None
    nodes: list[WorkflowNodeSnapshot]
    change_log: dict[str, Any] | None = None
    diff_summary: dict[str, Any] | None = None


class WorkflowPlanCatalogProtocol(Protocol):
    async def fetch_plan_source(self, workflow_id: str) -> WorkflowPlanSource | None: ...


@dataclass(slots=True)
class WorkflowPlannerRepository(WorkflowPlanCatalogProtocol):
    """Repository that loads workflow graphs + diffs from the shared data layer."""

    session: AsyncSession

    async def fetch_plan_source(self, workflow_id: str) -> WorkflowPlanSource | None:
        graph = await self._fetch_graph(workflow_id)
        if graph is None:
            return None
        version = self._select_active_version(graph)
        if version is None:
            return None
        nodes = [self._map_node(node) for node in version.nodes]
        version_label = version.to_version or version.from_version or graph.version
        diff_summary = await self._fetch_diff(graph.id, version_label)
        return WorkflowPlanSource(
            graph_id=str(graph.id),
            name=graph.name,
            domain=graph.domain,
            version=version_label,
            country_code=graph.country_code,
            nodes=nodes,
            change_log=version.change_log,
            diff_summary=diff_summary,
        )

    async def _fetch_graph(self, workflow_id: str) -> WorkflowGraph | None:
        stmt = (
            select(WorkflowGraph)
            .where(WorkflowGraph.id == _as_uuid(workflow_id))
            .options(selectinload(WorkflowGraph.versions).selectinload(WorkflowVersion.nodes))
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    def _select_active_version(self, graph: WorkflowGraph) -> WorkflowVersion | None:
        if not graph.versions:
            return None
        target_version = graph.version
        if target_version:
            for version in graph.versions:
                label = version.to_version or version.from_version
                if label == target_version:
                    return version
        fallback_timestamp = datetime.min.replace(tzinfo=UTC)
        sorted_versions = sorted(
            graph.versions,
            key=lambda version: version.created_at or fallback_timestamp,
            reverse=True,
        )
        return sorted_versions[0] if sorted_versions else None

    async def _fetch_diff(self, graph_id: UUID, to_version: str | None) -> dict[str, Any] | None:
        if not to_version:
            return None
        stmt = text(
            """
            SELECT workflow_graph_id, from_version, to_version, added_nodes, removed_nodes,
                   edge_changes, approver, last_refreshed_at
            FROM workflow_version_diffs
            WHERE workflow_graph_id = :graph_id AND to_version = :to_version
            ORDER BY last_refreshed_at DESC
            LIMIT 1
            """
        )
        result = await self.session.execute(stmt, {"graph_id": graph_id, "to_version": to_version})
        row = result.mappings().first()
        if row is None:
            return None
        return {
            "workflow_graph_id": str(row["workflow_graph_id"]),
            "from_version": row.get("from_version"),
            "to_version": row.get("to_version"),
            "added_nodes": row.get("added_nodes") or [],
            "removed_nodes": row.get("removed_nodes") or [],
            "edge_changes": row.get("edge_changes") or [],
            "approver": str(row["approver"]) if row.get("approver") else None,
            "last_refreshed_at": row.get("last_refreshed_at"),
        }

    def _map_node(self, node: WorkflowNode) -> WorkflowNodeSnapshot:
        return WorkflowNodeSnapshot(
            key=node.node_key,
            path=str(node.path),
            description=node.description,
            preconditions=node.preconditions or {},
            tool_hints=list(node.tool_hints or []),
            artifacts=node.artifacts or {},
        )


def _as_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


__all__ = [
    "WorkflowNodeSnapshot",
    "WorkflowPlanCatalogProtocol",
    "WorkflowPlanSource",
    "WorkflowPlannerRepository",
]
