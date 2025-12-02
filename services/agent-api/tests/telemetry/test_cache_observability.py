from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from prometheus_client import CollectorRegistry
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import (
    Chunk,
    ChunkMetrics,
    PillarAnswer,
    PillarAnswerSource,
    RetrievalRun,
    RetrievalRunItem,
)
from sqlalchemy import select

from cache.response_serializer import CacheCitation, CacheResponsePayload
from guardrails.models import RouterRoute
from models.retrieval import AttachmentDocument, AttachmentScope, NormalizedInput, TenantScope
from state.agent_state import AgentState, CacheMetadata, MessageSnapshot
from telemetry.cache_observability import CacheObservability
from telemetry.metrics_registry import MetricsRegistry

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _create_document_with_chunk(db_session):
    document = Document(
        owner_user_id=uuid4(),
        access_scope="user_private",
        canonical_name="Test Document",
        country_code="USA",
        language="en",
        status="active",
        ingestion_stage="activate",
        content_hash=uuid4().hex,
    )
    db_session.add(document)
    await db_session.flush()
    chunk = Chunk(
        document_id=document.id,
        position=0,
        chunk_type="text",
        text_content="evidence",
        content_hash=uuid4().hex,
        owner_user_id=document.owner_user_id,
        country_code=document.country_code or "USA",
    )
    db_session.add(chunk)
    await db_session.flush()
    return document, chunk


async def test_cache_observability_persists_shared_data_layer_writes(db_session) -> None:
    document, chunk = await _create_document_with_chunk(db_session)
    cache_obs = CacheObservability(metrics=MetricsRegistry(registry=CollectorRegistry()))
    normalized_input = NormalizedInput(
        normalized_prompt="Summarize findings",
        raw_prompt="Summarize findings",
        tenant_scope=TenantScope(
            conversation_id=str(document.id),
            thread_id="thread-1",
            owner_user_id=str(document.owner_user_id),
            country_code=document.country_code,
        ),
        attachment_refs=[],
        scope_hash="scope-1",
    )
    state = AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id=str(uuid4()),
        normalized_input=normalized_input,
        attachment_scope=AttachmentScope(
            documents=[
                AttachmentDocument(
                    document_id=str(document.id),
                    access_scope=document.access_scope,
                    country_code=document.country_code,
                )
            ],
            workflows=[],
        ),
        cache_metadata=CacheMetadata(cache_key="agent-api:retrieval:test"),
        route=RouterRoute.INFORMATIONAL,
        quality_score=0.92,
    )
    citation = CacheCitation(
        doc_id=str(document.id),
        chunk_id=str(chunk.id),
        snippet="evidence",
        score=0.87,
        metadata={"country_code": document.country_code},
    )
    payload = CacheResponsePayload(
        answer_text="Final answer",
        citations=[citation],
        chunk_ids=[citation.chunk_id],
        model_metadata={"model": "gpt-5"},
    )

    await cache_obs.record_cache_hit(
        cache_key="agent-api:retrieval:test",
        route="informational",
        latency_ms=2.0,
    )
    await cache_obs.record_cache_write(
        cache_key="agent-api:retrieval:test",
        route="informational",
        ttl_seconds=86400,
        session=db_session,
        state=state,
        payload=payload,
    )

    stats = cache_obs.snapshot_valkey_stats()
    assert stats["hits"] == 1
    assert stats["writes"] == 1

    run = (await db_session.execute(select(RetrievalRun))).scalars().one()
    assert run.query_text == "Summarize findings"
    items = (await db_session.execute(select(RetrievalRunItem))).scalars().all()
    assert len(items) == 1
    assert items[0].chunk_id == chunk.id

    chunk_metric = (await db_session.execute(select(ChunkMetrics))).scalars().one()
    assert chunk_metric.chunk_id == chunk.id
    assert chunk_metric.retrieval_count == 1

    pillar_answer = (await db_session.execute(select(PillarAnswer))).scalars().one()
    assert pillar_answer.summary_markdown == "Final answer"
    sources = (await db_session.execute(select(PillarAnswerSource))).scalars().all()
    assert len(sources) == 1
    assert sources[0].chunk_id == chunk.id
