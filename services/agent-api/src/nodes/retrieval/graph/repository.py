from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from shared_data_layer.db.models import (
    GraphEdge,
    GraphEdgeEvidenceRollup,
    GraphEntity,
    GraphHotEntity,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.graph.config import GraphRefreshSettings
from nodes.retrieval.graph.models import (
    GraphEntityRecord,
    GraphFilterContext,
    GraphRelationRecord,
    GraphRetrievalResult,
)


class GraphRepositoryProtocol(Protocol):
    async def fetch_graph(
        self,
        *,
        filters: GraphFilterContext,
        settings: GraphRefreshSettings,
    ) -> GraphRetrievalResult: ...


@dataclass(slots=True)
class GraphDataRepository(GraphRepositoryProtocol):
    """Query helpers for graph_* tables/materialized views."""

    session: AsyncSession

    async def fetch_graph(
        self,
        *,
        filters: GraphFilterContext,
        settings: GraphRefreshSettings,
    ) -> GraphRetrievalResult:
        entities = await self._fetch_entities(filters, settings)
        if not entities:
            return GraphRetrievalResult()
        relations = await self._fetch_relations(filters, settings, entities)
        algo_version = next(
            (entity.algo_version for entity in entities if entity.algo_version), None
        )
        return GraphRetrievalResult(
            entities=entities, relations=relations, algo_version=algo_version
        )

    async def _fetch_entities(
        self,
        filters: GraphFilterContext,
        settings: GraphRefreshSettings,
    ) -> list[GraphEntityRecord]:
        doc_ids = _coerce_uuid_list(filters.document_ids)
        owner_uuid = _as_uuid(filters.owner_user_id)
        stmt = select(
            GraphEntity.id,
            GraphEntity.name,
            GraphEntity.description,
            GraphEntity.score,
            GraphEntity.labels,
            GraphEntity.document_id,
            GraphEntity.country_code,
            GraphEntity.owner_user_id,
            GraphEntity.algo_version,
            GraphHotEntity.hot_rank,
        ).join(
            GraphHotEntity,
            and_(
                GraphHotEntity.id == GraphEntity.id,
                GraphHotEntity.country_code == GraphEntity.country_code,
            ),
        )
        stmt = self._apply_entity_filters(stmt, filters, owner_uuid, doc_ids)
        stmt = stmt.order_by(GraphHotEntity.hot_rank.asc(), GraphEntity.last_seen_at.desc())
        stmt = stmt.limit(settings.max_entities)
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            raise NodeError(
                code="GRAPH_ENTITIES_MISSING",
                message="No hot-ranked graph entities available for the request",
                details={"document_ids": [str(doc_id) for doc_id in doc_ids]},
            )
        return [
            GraphEntityRecord(
                entity_id=str(row.id),
                label=row.name,
                summary=row.description,
                score=float(row.score) if row.score is not None else None,
                document_ids=[str(row.document_id)] if row.document_id else [],
                labels=list(row.labels or []),
                country_code=row.country_code,
                owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
                hot_rank=row.hot_rank,
                algo_version=row.algo_version,
            )
            for row in rows
        ]

    async def _fetch_relations(
        self,
        filters: GraphFilterContext,
        settings: GraphRefreshSettings,
        entities: list[GraphEntityRecord],
    ) -> list[GraphRelationRecord]:
        entity_ids = _coerce_uuid_list([entity.entity_id for entity in entities])
        if not entity_ids:
            return []
        doc_ids = _coerce_uuid_list(filters.document_ids)
        owner_uuid = _as_uuid(filters.owner_user_id)
        source_alias = aliased(GraphEntity)
        target_alias = aliased(GraphEntity)
        stmt = (
            select(
                GraphEdge.id,
                GraphEdge.source_entity_id,
                GraphEdge.target_entity_id,
                GraphEdge.edge_type,
                GraphEdge.directional,
                GraphEdge.weight,
                GraphEdge.metadata_,
                GraphEdgeEvidenceRollup.evidence_chunk_ids,
                GraphEdgeEvidenceRollup.evidence_count,
                GraphEdgeEvidenceRollup.last_refreshed_at,
            )
            .join(GraphEdgeEvidenceRollup, GraphEdgeEvidenceRollup.edge_id == GraphEdge.id)
            .join(
                source_alias,
                and_(
                    GraphEdge.source_entity_id == source_alias.id,
                    GraphEdge.source_entity_country_code == source_alias.country_code,
                ),
            )
            .join(
                target_alias,
                and_(
                    GraphEdge.target_entity_id == target_alias.id,
                    GraphEdge.target_entity_country_code == target_alias.country_code,
                ),
            )
            .where(
                or_(
                    GraphEdge.source_entity_id.in_(entity_ids),
                    GraphEdge.target_entity_id.in_(entity_ids),
                )
            )
        )
        stmt = self._apply_relation_filters(
            stmt,
            filters,
            owner_uuid,
            doc_ids,
            source_alias,
            target_alias,
        )
        stmt = stmt.order_by(
            GraphEdge.last_seen_at.desc(), func.coalesce(GraphEdge.weight, 0).desc()
        )
        stmt = stmt.limit(settings.max_relations)
        rows = (await self.session.execute(stmt)).all()
        return [
            GraphRelationRecord(
                relation_id=str(row.id),
                source_entity_id=str(row.source_entity_id),
                target_entity_id=str(row.target_entity_id),
                relation_type=row.edge_type,
                directional=row.directional,
                weight=float(row.weight) if row.weight is not None else None,
                evidence_chunk_ids=[str(chunk_id) for chunk_id in row.evidence_chunk_ids or []],
                evidence_count=row.evidence_count,
                last_refreshed_at=row.last_refreshed_at,
                metadata=row.metadata_ or {},
            )
            for row in rows
        ]

    def _apply_entity_filters(
        self,
        stmt: Select,
        filters: GraphFilterContext,
        owner_uuid: UUID | None,
        doc_ids: list[UUID],
    ) -> Select:
        if filters.country_codes:
            stmt = stmt.where(GraphEntity.country_code.in_(filters.country_codes))
        if doc_ids:
            stmt = stmt.where(GraphEntity.document_id.in_(doc_ids))
        if filters.intent_tags:
            stmt = stmt.where(GraphEntity.labels.op("&&")(list(filters.intent_tags)))
        stmt = stmt.where(_owner_clause(GraphEntity, owner_uuid))
        return stmt

    def _apply_relation_filters(
        self,
        stmt: Select,
        filters: GraphFilterContext,
        owner_uuid: UUID | None,
        doc_ids: list[UUID],
        source_alias,
        target_alias,
    ) -> Select:
        if filters.country_codes:
            stmt = stmt.where(source_alias.country_code.in_(filters.country_codes))
            stmt = stmt.where(target_alias.country_code.in_(filters.country_codes))
        if doc_ids:
            stmt = stmt.where(
                or_(
                    source_alias.document_id.in_(doc_ids),
                    target_alias.document_id.in_(doc_ids),
                )
            )
        stmt = stmt.where(_owner_clause(source_alias, owner_uuid))
        stmt = stmt.where(_owner_clause(target_alias, owner_uuid))
        if filters.intent_tags:
            stmt = stmt.where(
                or_(
                    source_alias.labels.op("&&")(list(filters.intent_tags)),
                    target_alias.labels.op("&&")(list(filters.intent_tags)),
                )
            )
        return stmt


def _owner_clause(model, owner_uuid: UUID | None):
    if owner_uuid:
        return or_(model.owner_user_id.is_(None), model.owner_user_id == owner_uuid)
    return model.owner_user_id.is_(None)


def _as_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    return UUID(str(value))


def _coerce_uuid_list(values: Sequence[str] | Iterable[str]) -> list[UUID]:
    uuids: list[UUID] = []
    for value in values:
        try:
            uuids.append(UUID(str(value)))
        except Exception:  # pragma: no cover - defensive parsing
            continue
    return uuids
