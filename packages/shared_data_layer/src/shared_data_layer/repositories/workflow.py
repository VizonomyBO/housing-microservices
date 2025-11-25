from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.models.workflow import WorkflowGraph, WorkflowVersion
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.workflow import WorkflowGraphRead


class WorkflowGraphRepository(BaseRepository[WorkflowGraph]):
    def __init__(self, session):
        super().__init__(session, WorkflowGraph)

    async def get_published_workflow(self, domain: str, country_code: Optional[str] = None) -> Optional[WorkflowGraphRead]:
        stmt = (
            select(WorkflowGraph)
            .join(WorkflowGraph.versions)
            .where(WorkflowGraph.domain == domain)
            .where(WorkflowVersion.is_published == True)
            .options(
                selectinload(WorkflowGraph.versions).selectinload(WorkflowVersion.nodes),
                selectinload(WorkflowGraph.versions).selectinload(WorkflowVersion.edges)
            )
        )
        if country_code:
            stmt = stmt.where(WorkflowGraph.country_code == country_code)
            
        result = await self.session.execute(stmt)
        # This might return multiple if multiple graphs match, logic should handle preference.
        # For now return first.
        workflow = result.scalars().first()
        if workflow:
            return WorkflowGraphRead.model_validate(workflow)
        return None
