from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from shared_data_layer.db.maintenance import (
    refresh_graph_community_rollups,
    refresh_graph_edge_evidence_rollup,
    refresh_graph_hot_entities,
    refresh_graph_materializations,
)
from shared_data_layer.db.models.knowledge_graph import (
    GraphEdge,
    GraphEntity,
    GraphEvidence,
)
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.knowledge_graph import GraphEdgeRead, GraphEntityRead


class KnowledgeGraphRepository(BaseRepository[GraphEntity]):
    def __init__(self, session):
        super().__init__(session, GraphEntity)

    async def fetch_entity_with_neighbors(
        self, entity_id: UUID, depth: int = 1
    ) -> Optional[GraphEntityRead]:
        # Depth handling is complex in ORM, for now just load direct neighbors (depth=1)
        stmt = (
            select(GraphEntity)
            .where(GraphEntity.id == entity_id)
            .options(
                selectinload(GraphEntity.edges_out).options(
                    selectinload(GraphEdge.target), selectinload(GraphEdge.evidence)
                ),
                selectinload(GraphEntity.edges_in).options(
                    selectinload(GraphEdge.source), selectinload(GraphEdge.evidence)
                ),
            )
        )
        result = await self.session.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity:
            return GraphEntityRead.model_validate(entity)
        return None

    async def list_edges_for_scope(
        self, country_code: str, owner_user_id: Optional[UUID] = None
    ) -> List[GraphEdgeRead]:
        # This requires joining with Entity to filter by scope, or if Edge has
        # scope (it doesn't in my model, Entity does)
        # Assuming we want edges where source or target is in scope.
        stmt = (
            select(GraphEdge)
            .join(GraphEdge.source)
            .where(GraphEntity.country_code == country_code)
            # Merging labels would require custom SQL or array_cat, for now
            # just overwrite or keep existing if logic demands
            # "labels": stmt.excluded.labels
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
        """
        # Since we can't easily do conditional constraints in one INSERT
        # statement for different unique indexes without partial index
        # definitions matching exactly, we rely on the application logic or the
        # unique constraints defined in DB.

        # Assuming unique constraints are:
        # 1. (type, name, country_code) WHERE owner_user_id IS NULL
        # 2. (type, name, owner_user_id) WHERE owner_user_id IS NOT NULL
        # Prepare insert statement
        stmt = insert(GraphEntity).values(**entity_data)

        # Define update dict (merge labels, update timestamp)
        update_dict = {
            "description": stmt.excluded.description,
            "embedding": stmt.excluded.embedding,
            "updated_at": stmt.excluded.updated_at,
            # Merging labels would require custom SQL or array_cat, for now
            # just overwrite or keep existing if logic demands
            # "labels": stmt.excluded.labels
        }

        # We need to target the correct constraint.
        # SQLAlchemy requires naming the constraint or index for ON CONFLICT DO UPDATE.
        # Let's assume we try to match on the fields that form the unique key.

        if entity_data.get("owner_user_id"):
            # User scope
            index_elements = ["entity_type", "entity_key", "owner_user_id"]
        else:
            # Base scope
            index_elements = ["entity_type", "entity_key", "country_code"]

        stmt = stmt.on_conflict_do_update(
            index_elements=index_elements, set_=update_dict
        ).returning(GraphEntity)

        result = await self.session.execute(stmt)
        entity = result.scalar_one()

        # Refresh hot entities view as entity creation/update might affect it
        # (though mostly edges do). But if we update properties that might be
        # relevant later, or if we just want to be safe.
        # Actually hot entities is based on edge count, so mostly edges matter.
        # But if we add a new entity, it has 0 edges, so it might not appear in
        # top N anyway. Let's leave it for now or add it if we think it's needed.
        # The plan says "Call refresh_hot_entities in upsert_entity / upsert_edge".
        await self.refresh_hot_entities()

        return entity

    async def upsert_edge(self, edge_data: dict) -> GraphEdge:
        """
        Upsert a graph edge using
        (source_entity_id, target_entity_id, edge_type) as the unique key.
        """
        payload = edge_data.copy()
        if "source_entity_country_code" not in payload:
            payload["source_entity_country_code"] = await self._get_entity_country_code(
                payload["source_entity_id"]
            )
        if "target_entity_country_code" not in payload:
            payload["target_entity_country_code"] = await self._get_entity_country_code(
                payload.get("target_entity_id", payload["source_entity_id"])
            )

        stmt = insert(GraphEdge).values(**payload)

        update_dict = {
            "weight": stmt.excluded.weight,
            "evidence_span": stmt.excluded.evidence_span,
            "updated_at": stmt.excluded.updated_at,
        }

        stmt = stmt.on_conflict_do_update(
            index_elements=["source_entity_id", "target_entity_id", "edge_type"],
            set_=update_dict,
        ).returning(GraphEdge)

        result = await self.session.execute(stmt)
        edge = result.scalar_one()

        # Refresh hot entities as edge count changed (or might have if new edge)
        await self.refresh_hot_entities()

        return edge

    async def _get_entity_country_code(self, entity_id: UUID) -> str:
        result = await self.session.execute(
            select(GraphEntity.country_code).where(GraphEntity.id == entity_id)
        )
        country_code = result.scalar_one_or_none()
        if country_code is None:
            raise ValueError(f"GraphEntity {entity_id} not found")
        return country_code

    async def _resolve_chunk_country_code(self, chunk_id: UUID) -> str:
        result = await self.session.execute(
            select(Chunk.country_code).where(Chunk.id == chunk_id)
        )
        country_code = result.scalar_one_or_none()
        if country_code is None:
            raise ValueError(f"Chunk {chunk_id} not found when attaching evidence")
        return country_code

    async def add_evidence(
        self,
        edge_id: UUID,
        chunk_id: UUID,
        *,
        chunk_country_code: Optional[str] = None,
        offsets: Optional[tuple[int, int]] = None,
        confidence: Optional[float] = None,
        metadata: Optional[dict] = None,
    ) -> GraphEvidence:
        """
        Add evidence to an edge and refresh the rollup view.
        """
        if chunk_country_code is None:
            chunk_country_code = await self._resolve_chunk_country_code(chunk_id)

        evidence = GraphEvidence(
            edge_id=edge_id,
            chunk_id=chunk_id,
            chunk_country_code=chunk_country_code,
            offsets=offsets,
            confidence=confidence,
            metadata_=metadata,
        )
        self.session.add(evidence)
        await self.session.flush()

        await self.refresh_edge_evidence_rollup()

        return evidence

    async def refresh_edge_evidence_rollup(self, concurrently: bool = False) -> None:
        """
        Refresh the graph_edge_evidence_rollup materialized view.
        """
        await refresh_graph_edge_evidence_rollup(
            self.session, concurrently=concurrently
        )

    async def refresh_hot_entities(self, concurrently: bool = False) -> None:
        """
        Refresh the graph_hot_entities materialized view.
        """
        await refresh_graph_hot_entities(self.session, concurrently=concurrently)

    async def refresh_materializations(self, concurrently: bool = False) -> None:
        """Refresh both graph materialized views via the shared helper."""
        await refresh_graph_materializations(self.session, concurrently=concurrently)

    async def refresh_community_rollups(
        self,
        *,
        country_code: Optional[str] = None,
        algo_version: Optional[str] = None,
        community_id: Optional[UUID] = None,
    ) -> None:
        """Recompute `graph_communities` metrics for the requested slice."""

        await refresh_graph_community_rollups(
            self.session,
            country_code=country_code,
            algo_version=algo_version,
            community_id=community_id,
        )
