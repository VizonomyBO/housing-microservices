from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.models.knowledge_graph import GraphEntity, GraphEdge
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.knowledge_graph import GraphEntityRead, GraphEdgeRead


class KnowledgeGraphRepository(BaseRepository[GraphEntity]):
    def __init__(self, session):
        super().__init__(session, GraphEntity)

    async def fetch_entity_with_neighbors(self, entity_id: UUID, depth: int = 1) -> Optional[GraphEntityRead]:
        # Depth handling is complex in ORM, for now just load direct neighbors (depth=1)
        stmt = (
            select(GraphEntity)
            .where(GraphEntity.id == entity_id)
            .options(
                selectinload(GraphEntity.edges_out).options(selectinload(GraphEdge.target), selectinload(GraphEdge.evidence)),
                selectinload(GraphEntity.edges_in).options(selectinload(GraphEdge.source), selectinload(GraphEdge.evidence))
            )
        )
        result = await self.session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity:
            return GraphEntityRead.model_validate(entity)
        return None

    async def list_edges_for_scope(self, country_code: str, owner_user_id: Optional[UUID] = None) -> List[GraphEdgeRead]:
        # This requires joining with Entity to filter by scope, or if Edge has scope (it doesn't in my model, Entity does)
        # Assuming we want edges where source or target is in scope.
        stmt = (
            select(GraphEdge)
            .join(GraphEdge.source)
            .where(GraphEntity.country_code == country_code)
            .options(selectinload(GraphEdge.evidence))
        )
        if owner_user_id:
            stmt = stmt.where(GraphEntity.owner_user_id == owner_user_id)
            
        result = await self.session.execute(stmt)
        edges = result.scalars().all()
        return [GraphEdgeRead.model_validate(edge) for edge in edges]
