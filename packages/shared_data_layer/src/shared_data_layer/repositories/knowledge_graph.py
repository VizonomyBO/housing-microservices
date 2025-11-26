from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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

    async def upsert_entity(self, entity_data: dict) -> GraphEntity:
        """
        Upsert a graph entity.
        Conflict target depends on scope:
        - Base: (type, name, country_code) where owner_user_id IS NULL
        - User: (type, name, owner_user_id) where owner_user_id IS NOT NULL
        
        Since we can't easily do conditional constraints in one INSERT statement for different unique indexes 
        without partial index definitions matching exactly, we rely on the application logic or the unique constraints defined in DB.
        
        Assuming unique constraints are:
        1. (type, name, country_code) WHERE owner_user_id IS NULL
        2. (type, name, owner_user_id) WHERE owner_user_id IS NOT NULL
        """
        # Prepare insert statement
        stmt = insert(GraphEntity).values(**entity_data)
        
        # Define update dict (merge labels, update timestamp)
        update_dict = {
            "description": stmt.excluded.description,
            "embedding": stmt.excluded.embedding,
            "updated_at": stmt.excluded.updated_at,
            # Merging labels would require custom SQL or array_cat, for now just overwrite or keep existing if logic demands
            # "labels": stmt.excluded.labels 
        }
        
        # We need to target the correct constraint. 
        # SQLAlchemy requires naming the constraint or index for ON CONFLICT DO UPDATE.
        # Let's assume we try to match on the fields that form the unique key.
        
        if entity_data.get("owner_user_id"):
             # User scope
             index_elements = ["type", "name", "owner_user_id"]
        else:
             # Base scope
             index_elements = ["type", "name", "country_code"]

        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements,
            set_=update_dict
        ).returning(GraphEntity)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def upsert_edge(self, edge_data: dict) -> GraphEdge:
        """
        Upsert a graph edge.
        Unique constraint usually on (source_id, target_id, relation).
        """
        stmt = insert(GraphEdge).values(**edge_data)
        
        update_dict = {
            "weight": stmt.excluded.weight,
            "evidence_span": stmt.excluded.evidence_span,
            "updated_at": stmt.excluded.updated_at
        }
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_id", "target_id", "relation"],
            set_=update_dict
        ).returning(GraphEdge)
        
        result = await self.session.execute(stmt)
        return result.scalar_one()
