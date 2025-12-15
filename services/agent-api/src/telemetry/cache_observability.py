"""Cache observability helpers that bridge metrics + shared data layer writers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from shared_data_layer.db.models.retrieval import (
    ChunkMetrics,
    PillarAnswerSource,
    RetrievalRun,
    RetrievalRunItem,
)
from shared_data_layer.repositories.retrieval import PillarAnswerRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cache.response_serializer import CacheCitation, CacheResponsePayload
from state.agent_state import AgentState
from telemetry.metrics_registry import MetricsRegistry, get_metrics_registry


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


@dataclass(slots=True)
class RetrievalItemTelemetry:
    """Chunk-level telemetry used when persisting retrieval runs."""

    chunk_id: str
    chunk_country_code: str
    score: float
    rank: int


@dataclass(slots=True)
class CacheObservability:
    """Coordinates cache metrics, rate limiter stats, and telemetry writes."""

    metrics: MetricsRegistry = field(default_factory=get_metrics_registry)
    namespace: str = "agent-api"
    pool_counters: dict[str, float] = field(
        default_factory=lambda: {"hits": 0.0, "misses": 0.0, "writes": 0.0}
    )

    async def record_cache_hit(
        self,
        *,
        cache_key: str,
        route: str | None,
        latency_ms: float | None = None,
    ) -> None:
        self.pool_counters["hits"] += 1
        latency_seconds = latency_ms / 1000 if latency_ms is not None else None
        self.metrics.record_cache_event(
            event="hit",
            namespace=self.namespace,
            route=route,
            latency_seconds=latency_seconds,
        )

    async def record_cache_miss(
        self,
        *,
        cache_key: str,
        route: str | None,
        reason: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        self.pool_counters["misses"] += 1
        if reason:
            key = f"miss:{reason}"
            self.pool_counters[key] = self.pool_counters.get(key, 0.0) + 1
        latency_seconds = latency_ms / 1000 if latency_ms is not None else None
        self.metrics.record_cache_event(
            event="miss",
            namespace=self.namespace,
            route=route,
            latency_seconds=latency_seconds,
        )

    async def record_cache_write(
        self,
        *,
        cache_key: str,
        route: str | None,
        ttl_seconds: int | None,
        session: AsyncSession | None = None,
        state: AgentState | None = None,
        payload: CacheResponsePayload | None = None,
    ) -> None:
        self.pool_counters["writes"] += 1
        self.metrics.record_cache_event(
            event="write",
            namespace=self.namespace,
            route=route,
            ttl_seconds=float(ttl_seconds) if ttl_seconds is not None else None,
        )
        if session is None or state is None or payload is None:
            return
        await self._persist_retrieval_run(session=session, state=state, payload=payload)
        await self._persist_chunk_metrics(session=session, state=state, payload=payload)
        await self._persist_pillar_answer(session=session, state=state, payload=payload)

    def snapshot_valkey_stats(self) -> Mapping[str, float]:
        return dict(self.pool_counters)

    async def _persist_retrieval_run(
        self,
        *,
        session: AsyncSession,
        state: AgentState,
        payload: CacheResponsePayload,
    ) -> None:
        normalized = state.normalized_input
        if normalized is None:
            return
        chunk_items = list(self._chunk_items_from_payload(state, payload))
        if not chunk_items:
            return
        run = RetrievalRun(
            query_text=normalized.normalized_prompt,
            filters={
                "route": state.route.value if state.route else None,
                "intent_tags": list(normalized.intent_tags),
            },
            document_scope=self._document_scope(state),
            top_k=len(chunk_items),
        )
        session.add(run)
        await session.flush()
        for item in chunk_items:
            chunk_uuid = _as_uuid(item.chunk_id)
            if chunk_uuid is None:
                continue
            session.add(
                RetrievalRunItem(
                    run_id=run.id,
                    chunk_id=chunk_uuid,
                    chunk_country_code=item.chunk_country_code,
                    score=item.score,
                    rank=item.rank,
                )
            )
        await session.flush()

    async def _persist_chunk_metrics(
        self,
        *,
        session: AsyncSession,
        state: AgentState,
        payload: CacheResponsePayload,
    ) -> None:
        tenant_country = self._tenant_country(state)
        for citation in payload.citations:
            chunk_uuid = _as_uuid(citation.chunk_id)
            if chunk_uuid is None:
                continue
            country_code = self._citation_country_code(citation, state, fallback=tenant_country)
            if country_code is None:
                continue
            metrics = await session.execute(
                select(ChunkMetrics).where(
                    ChunkMetrics.chunk_id == chunk_uuid,
                    ChunkMetrics.chunk_country_code == country_code,
                )
            )
            row = metrics.scalar_one_or_none()
            if row is None:
                row = ChunkMetrics(
                    chunk_id=chunk_uuid,
                    chunk_country_code=country_code,
                    retrieval_count=0,
                )
                session.add(row)
            row.retrieval_count += 1
            row.last_seen_at = _utc_now()
            if citation.score is not None:
                row.quality_score = citation.score
        await session.flush()

    async def _persist_pillar_answer(
        self,
        *,
        session: AsyncSession,
        state: AgentState,
        payload: CacheResponsePayload,
    ) -> None:
        normalized = state.normalized_input
        if normalized is None or not payload.answer_text:
            return
        tenant = normalized.tenant_scope
        owner_uuid = _as_uuid(tenant.owner_user_id)
        country_code = tenant.country_code
        document_uuid = self._first_valid_doc_uuid(payload.citations)
        if owner_uuid is None or country_code is None or document_uuid is None:
            return
        repo = PillarAnswerRepository(session)
        content_hash = hashlib.sha256(payload.answer_text.encode("utf-8")).hexdigest()
        answer = await repo.create_pillar_answer(
            owner_user_id=owner_uuid,
            document_id=document_uuid,
            country_code=country_code,
            pillar_name=(state.route.value if state.route else "informational"),
            content_hash=content_hash,
            summary_markdown=payload.answer_text,
            answer_json={
                "answer": payload.answer_text,
                "citations": [
                    c.model_dump(mode="json", exclude_none=True) for c in payload.citations
                ],
                "model_metadata": payload.model_metadata,
            },
            status="draft",
            score=state.quality_score,
            generated_at=payload.created_at,
        )
        for citation in payload.citations:
            chunk_uuid = _as_uuid(citation.chunk_id)
            if chunk_uuid is None:
                continue
            country = self._citation_country_code(citation, state, fallback=country_code)
            if country is None:
                continue
            session.add(
                PillarAnswerSource(
                    pillar_answer_id=answer.id,
                    chunk_id=chunk_uuid,
                    chunk_country_code=country,
                    contribution_type=citation.metadata.get("contribution_type", "evidence"),
                    weight=float(citation.metadata.get("weight", 1.0)),
                    evidence_text=citation.snippet or citation.metadata.get("snippet", ""),
                    page_number=citation.metadata.get("page"),
                )
            )
        await session.flush()

    def _chunk_items_from_payload(
        self, state: AgentState, payload: CacheResponsePayload
    ) -> Iterable[RetrievalItemTelemetry]:
        country_map = self._document_country_map(state)
        citation_map = {citation.chunk_id: citation for citation in payload.citations}
        for rank, chunk_id in enumerate(payload.chunk_ids, start=1):
            citation = citation_map.get(chunk_id)
            score = citation.score if citation and citation.score is not None else 0.0
            country_code = None
            if citation is not None:
                country_code = self._citation_country_code(citation, state, fallback=None)
            if country_code is None and citation is not None and citation.doc_id:
                country_code = country_map.get(citation.doc_id)
            if country_code is None:
                country_code = self._tenant_country(state)
            if country_code is None:
                continue
            yield RetrievalItemTelemetry(
                chunk_id=chunk_id,
                chunk_country_code=country_code,
                score=float(score),
                rank=rank,
            )

    def _document_scope(self, state: AgentState) -> Mapping[str, list[str]]:
        documents = state.attachment_scope.documents if state.attachment_scope else []
        workflows = state.attachment_scope.workflows if state.attachment_scope else []
        return {
            "documents": [doc.document_id for doc in documents if doc.document_id],
            "workflows": [wf.workflow_id for wf in workflows if wf.workflow_id],
        }

    def _document_country_map(self, state: AgentState) -> Mapping[str, str]:
        documents = state.attachment_scope.documents if state.attachment_scope else []
        return {
            doc.document_id: doc.country_code
            for doc in documents
            if doc.document_id and doc.country_code
        }

    def _citation_country_code(
        self,
        citation: CacheCitation,
        state: AgentState,
        *,
        fallback: str | None,
    ) -> str | None:
        metadata_country = citation.metadata.get("country_code")
        if metadata_country:
            return metadata_country
        documents = self._document_country_map(state)
        if citation.doc_id and citation.doc_id in documents:
            return documents[citation.doc_id]
        return fallback

    def _tenant_country(self, state: AgentState) -> str | None:
        normalized = state.normalized_input
        if normalized and normalized.tenant_scope.country_code:
            return normalized.tenant_scope.country_code
        return None

    def _first_valid_doc_uuid(self, citations: Sequence[CacheCitation]) -> UUID | None:
        for citation in citations:
            doc_uuid = _as_uuid(citation.doc_id)
            if doc_uuid is not None:
                return doc_uuid
        return None


__all__ = ["CacheObservability", "RetrievalItemTelemetry"]
