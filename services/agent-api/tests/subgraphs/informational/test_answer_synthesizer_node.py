from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from cache import (
    CacheCitation,
    CacheResponsePayload,
    CacheWriter,
    InMemoryValkeyClient,
)
from cache.response_serializer import CacheWorkflowPlanExcerpt
from models.retrieval import NormalizedInput, TenantScope
from nodes.retrieval.exceptions import NodeError
from state.agent_state import AgentState, CacheMetadata, MessageSnapshot
from subgraphs.informational.answer_synthesizer_node import (
    AnswerSynthesisContext,
    AnswerSynthesisResult,
    AnswerSynthesizerNode,
)


class StubComposer:
    def __init__(self, *, answer_text: str = "fresh answer") -> None:
        self.calls = 0
        self.answer_text = answer_text

    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:  # type: ignore[override]
        self.calls += 1
        return AnswerSynthesisResult(
            answer_text=self.answer_text,
            citations=[CacheCitation(doc_id="doc-1", chunk_id="chunk-1", snippet="evidence")],
            chunk_ids=["chunk-1"],
            quality_score=0.92,
            model_metadata={"model": "stub"},
            workflow_excerpt=CacheWorkflowPlanExcerpt(
                plan_id="wf-1", version="v1", steps=["Assess"], summary="summary"
            ),
        )


class FailComposer(StubComposer):
    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:  # type: ignore[override]
        raise AssertionError("Composer should not be called when cache hits")


def _base_state(cache_metadata: CacheMetadata | None = None) -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Explain the findings",
        raw_prompt="Explain the findings",
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[],
        scope_hash="scope",
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
        normalized_input=normalized,
        cache_metadata=cache_metadata or CacheMetadata(cache_key="agent-api:retrieval:conv-1"),
    )


@pytest.mark.asyncio
async def test_cache_hit_short_circuits_generation() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-cache")
    state = _base_state(cache_metadata=metadata)
    writer = CacheWriter(client=client)
    payload = CacheResponsePayload(
        answer_text="cached",
        citations=[CacheCitation(doc_id="doc-a", chunk_id="chunk-a")],
        chunk_ids=["chunk-a"],
        model_metadata={"quality_score": 0.88},
    )
    await writer.write(payload=payload, cache_metadata=metadata)
    node = AnswerSynthesizerNode(composer=FailComposer(), cache_client=client)

    updates = await node(state)

    assert updates["answer"] == "cached"
    assert updates["cache_metadata"].hit is True
    assert updates["citations"][0].doc_id == "doc-a"


@pytest.mark.asyncio
async def test_generates_answer_on_cache_miss() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-miss")
    state = _base_state(cache_metadata=metadata)
    composer = StubComposer()
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    assert composer.calls == 1
    assert updates["answer"] == "fresh answer"
    assert updates["quality_score"] == pytest.approx(0.92)
    assert updates["cache_metadata"].hit is False


@pytest.mark.asyncio
async def test_requires_sql_without_trace_raises() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-trace")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = True
    composer = StubComposer()
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    with pytest.raises(NodeError):
        await node(state)


@pytest.mark.asyncio
async def test_sql_trace_adds_citation_when_required() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-trace-present")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = True
    state.numerical_trace = {
        "sql_queries": ["SELECT city FROM ledger"],
        "executor": {"row_count": 2},
        "table_specs": [{"table_id": "tbl-ledger", "alias": "ledger"}],
        "table_results": [{"city": "Austin"}],
    }
    state.numerical_result_rows = [{"city": "Austin"}]
    composer = StubComposer()
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    sql_citations = [c for c in updates["citations"] if c.doc_id == "SQL_RESULT"]
    assert sql_citations
    assert sql_citations[0].metadata["table_id"] == "tbl-ledger"
