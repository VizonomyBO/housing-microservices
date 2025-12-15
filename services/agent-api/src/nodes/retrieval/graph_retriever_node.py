"""GraphRetriever LangGraph node."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from models.retrieval import AttachmentScope
from nodes.retrieval.exceptions import InputNormalizationError
from nodes.retrieval.graph.config import GraphRefreshSettings
from nodes.retrieval.graph.models import GraphEntityRecord, GraphFilterContext
from nodes.retrieval.graph.repository import GraphRepositoryProtocol
from nodes.retrieval.graph.telemetry import (
    GraphRetrievalTelemetry,
    NoOpGraphRetrievalTelemetry,
)
from state.agent_state import (
    AgentState,
    GraphContext,
    GraphEntitySummary,
    GraphRelationSummary,
)
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_telemetry_snapshot, lifecycle_span


@dataclass(slots=True)
class GraphRetrieverNode:
    """Loads graph neighborhoods + relations for downstream prompt builders."""

    graph_repository: GraphRepositoryProtocol
    settings: GraphRefreshSettings = field(default_factory=GraphRefreshSettings)
    telemetry: GraphRetrievalTelemetry = field(default_factory=NoOpGraphRetrievalTelemetry)
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    force_refresh: bool = False

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        normalized_input = state.normalized_input
        attachment_scope = state.attachment_scope
        if normalized_input is None:
            raise InputNormalizationError(
                code="NORMALIZED_INPUT_MISSING",
                message="InputNormalizer must run before GraphRetriever",
            )
        if attachment_scope is None:
            raise InputNormalizationError(
                code="ATTACHMENT_SCOPE_MISSING",
                message="AttachmentScopeLoader must run before GraphRetriever",
            )
        filters = self._build_filters(
            normalized_input.scope_hash,
            normalized_input.intent_tags,
            attachment_scope,
            normalized_input.tenant_scope.country_code,
            normalized_input.tenant_scope.owner_user_id,
        )
        now = self.clock()
        current_context = state.graph_context or GraphContext()

        async with lifecycle_span(
            emitter=sse_emitter,
            node="graph_retriever",
            subgraph="retrieval",
            metadata={"scope_hash": filters.scope_hash, "force_refresh": self.force_refresh},
        ):
            if not self._should_refresh(current_context, filters, now):
                self.telemetry.record_hit(
                    scope_hash=filters.scope_hash, ttl_seconds=current_context.refresh_ttl_seconds
                )
                await emit_telemetry_snapshot(
                    sse_emitter,
                    metrics={"graph.cache.hit": 1},
                    labels={"scope_hash": filters.scope_hash or "none"},
                )
                return {}

            result = await self.graph_repository.fetch_graph(
                filters=filters, settings=self.settings
            )
            if result.entities or result.relations:
                self.telemetry.record_miss(scope_hash=filters.scope_hash, reason="refresh")
            else:
                self.telemetry.record_miss(scope_hash=filters.scope_hash, reason="empty")
            await emit_telemetry_snapshot(
                sse_emitter,
                metrics={"graph.cache.miss": 1},
                labels={"scope_hash": filters.scope_hash or "none"},
            )
            add_metadata(entity_count=len(result.entities), relation_count=len(result.relations))

            expires_at = now + timedelta(seconds=self.settings.ttl_seconds)
            graph_context = GraphContext(
                clusters=[self._map_entity(record) for record in result.entities],
                relations=[
                    GraphRelationSummary(
                        relation_id=str(relation.relation_id),
                        source_entity_id=str(relation.source_entity_id),
                        target_entity_id=str(relation.target_entity_id),
                        relation_type=relation.relation_type,
                        directional=relation.directional,
                        weight=relation.weight,
                        evidence_chunk_ids=relation.evidence_chunk_ids,
                        evidence_count=relation.evidence_count,
                        last_refreshed_at=relation.last_refreshed_at,
                        metadata=relation.metadata or {},
                    )
                    for relation in result.relations
                ],
                workflow_plan_version=current_context.workflow_plan_version,
                algo_version=result.algo_version or current_context.algo_version,
                scope_hash=filters.scope_hash,
                intent_tags=list(filters.intent_tags),
                fetched_at=now,
                expires_at=expires_at,
                refresh_ttl_seconds=self.settings.ttl_seconds,
                telemetry={
                    "cache_event": "refresh" if result.entities or result.relations else "empty"
                },
            )
            return {"graph_context": graph_context}

    def _should_refresh(
        self,
        graph_context: GraphContext,
        filters: GraphFilterContext,
        now: datetime,
    ) -> bool:
        if self.force_refresh or filters.refresh_requested:
            return True
        if graph_context.scope_hash != filters.scope_hash:
            return True
        if list(graph_context.intent_tags or []) != list(filters.intent_tags):
            return True
        return graph_context.expires_at is None or graph_context.expires_at <= now

    def _build_filters(
        self,
        scope_hash: str | None,
        intent_tags: list[str],
        attachment_scope: AttachmentScope,
        conversation_country: str | None,
        owner_user_id: str | None,
    ) -> GraphFilterContext:
        document_ids = [doc.document_id for doc in attachment_scope.documents if doc.document_id]
        country_codes = {doc.country_code for doc in attachment_scope.documents if doc.country_code}
        if not country_codes and conversation_country:
            country_codes = {conversation_country}
        return GraphFilterContext(
            scope_hash=scope_hash,
            intent_tags=intent_tags,
            document_ids=document_ids,
            country_codes=list(country_codes),
            owner_user_id=owner_user_id,
            refresh_requested=self.force_refresh,
        )

    def _map_entity(self, record: GraphEntityRecord) -> GraphEntitySummary:
        return GraphEntitySummary(
            entity_id=str(record.entity_id),
            label=record.label,
            summary=record.summary,
            score=record.score,
            document_ids=list(record.document_ids),
            labels=list(record.labels),
            country_code=record.country_code,
            owner_user_id=record.owner_user_id,
            hot_rank=record.hot_rank,
        )
