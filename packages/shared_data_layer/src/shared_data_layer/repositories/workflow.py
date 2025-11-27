from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.procedures import workflow_nodes_move_subtree
from shared_data_layer.db.models.workflow import WorkflowGraph, WorkflowVersion
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.workflow import WorkflowGraphRead


class WorkflowGraphRepository(BaseRepository[WorkflowGraph]):
    def __init__(self, session):
        super().__init__(session, WorkflowGraph)

    async def get_published_workflow(
        self, domain: str, country_code: Optional[str] = None
    ) -> Optional[WorkflowGraphRead]:
        stmt = (
            select(WorkflowGraph)
            .where(WorkflowGraph.domain == domain)
            .where(WorkflowGraph.status == "published")
            .options(
                selectinload(WorkflowGraph.versions).selectinload(
                    WorkflowVersion.nodes
                ),
                selectinload(WorkflowGraph.versions).selectinload(
                    WorkflowVersion.edges
                ),
            )
        )
        if country_code:
            stmt = stmt.where(WorkflowGraph.country_code == country_code)

        result = await self.session.execute(
            stmt.order_by(WorkflowGraph.published_at.desc())
        )
        # This might return multiple if multiple graphs match, logic should
        # handle preference. For now return first.
        workflow = result.scalars().first()
        if workflow:
            return WorkflowGraphRead.model_validate(workflow)
        return None

    async def move_subtree(
        self, graph_id: UUID, source_path: str, target_parent_path: str
    ) -> None:
        """
        Move a subtree within a workflow version using the stored procedure.

        Args:
            version_id: The workflow version ID.
            source_path: The ltree path of the subtree root to move (e.g. "A.B").
            target_parent_path: The ltree path of the new parent (e.g. "A.D").
        """
        await workflow_nodes_move_subtree(
            self.session,
            graph_id=graph_id,
            source_path=source_path,
            target_parent_path=target_parent_path,
        )
        # We don't commit here, letting the unit of work handle it,
        # but we should probably expire objects to ensure consistency if they are
        # loaded. However, repository methods usually don't expire all.
        # The caller should handle session lifecycle or we assume this is part
        # of a larger transaction. But since this modifies data via SP
        # (side-effecting SQL), the ORM doesn't know about it.
        # It's safer to expire relevant objects or all.
        # Let's expire all for safety in this specific operation.
        self.session.expire_all()
