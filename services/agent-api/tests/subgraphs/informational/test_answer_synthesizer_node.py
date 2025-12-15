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
    def __init__(
        self,
        *,
        answer_text: str = "fresh answer",
        citations: list[CacheCitation] | None = None,
    ) -> None:
        self.calls = 0
        self.answer_text = answer_text
        self.citations = citations or [
            CacheCitation(doc_id="doc-1", chunk_id="chunk-1", snippet="evidence")
        ]

    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:  # type: ignore[override]
        self.calls += 1
        return AnswerSynthesisResult(
            answer_text=self.answer_text,
            citations=self.citations,
            chunk_ids=[c.chunk_id for c in self.citations],
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
    assert "[SQL_ROWS]" in updates["answer"]
    assert "city=Austin" not in updates["answer"]


@pytest.mark.asyncio
async def test_sql_rows_marker_added_without_inline_dump() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-sql-rows")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = True
    rows = [
        {"city": "Austin", "value": 82},
        {"city": "Denton", "value": 71},
    ]
    state.numerical_trace = {
        "sql_queries": ["SELECT city, value FROM ledger"],
        "executor": {"row_count": len(rows)},
        "table_specs": [{"table_id": "tbl-ledger", "alias": "ledger"}],
        "table_results": rows,
    }
    state.numerical_result_rows = rows
    composer = StubComposer(answer_text="Summary of KPI insights.")
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    answer = updates["answer"]
    assert answer.endswith("[SQL_ROWS]")
    assert "city=Austin" not in answer
    assert "value=71" not in answer


@pytest.mark.asyncio
async def test_strips_inline_sql_row_dump() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-sql-inline")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = True
    rows = [{"city": "Austin", "value": 82}]
    state.numerical_trace = {
        "sql_queries": ["SELECT city, value FROM ledger"],
        "executor": {"row_count": len(rows)},
        "table_specs": [{"table_id": "tbl-ledger", "alias": "ledger"}],
        "table_results": rows,
    }
    state.numerical_result_rows = rows
    composer = StubComposer(
        answer_text="Summary of KPI insights.\n\n[SQL_ROWS]\n- city=Austin, value=82\n- city=Denton, value=71"
    )
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    answer = updates["answer"]
    assert answer.rstrip().endswith("[SQL_ROWS]")
    assert "city=Austin" not in answer
    assert "city=Denton" not in answer


@pytest.mark.asyncio
async def test_doc_placeholders_normalized_to_numeric() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-doc-markers")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = False
    citations = [
        CacheCitation(
            doc_id="doc-alpha",
            chunk_id="chunk-a",
            snippet="a",
            metadata={"document_alias": "DOC_ALPHA"},
        ),
        CacheCitation(
            doc_id="doc-beta",
            chunk_id="chunk-b",
            snippet="b",
            metadata={"document_alias": "DOC_BETA"},
        ),
    ]
    composer = StubComposer(
        answer_text="Summary cites [DOC_KPI] and the memo [DOC_POLICY].",
        citations=citations,
    )
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    answer = updates["answer"]
    assert "[DOC_KPI]" not in answer
    assert "[DOC_POLICY]" not in answer
    assert "[1]" in answer
    assert "[2]" in answer
    inline = updates["answer_metadata"]["inline_citations"]
    assert inline[0]["citation_index"] == 0
    assert inline[0]["citation_key"] == "c1"
    assert inline[0]["footnote"] == 1
    assert inline[1]["citation_index"] == 1
    assert inline[1]["citation_key"] == "c2"
    assert inline[1]["footnote"] == 2
    assert updates["citations"][0].metadata["footnote"] == 1
    assert updates["citations"][1].metadata["footnote"] == 2


@pytest.mark.asyncio
async def test_doc_placeholders_use_alias_mapping_even_out_of_order() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv-doc-order")
    state = _base_state(cache_metadata=metadata)
    state.requires_sql = False
    citations = [
        CacheCitation(
            doc_id="doc-policy",
            chunk_id="chunk-policy",
            snippet="policy memo",
            metadata={"document_alias": "DOC_POLICY"},
        ),
        CacheCitation(
            doc_id="doc-kpi",
            chunk_id="chunk-kpi",
            snippet="kpi dashboard",
            metadata={"document_alias": "DOC_KPI"},
        ),
    ]
    composer = StubComposer(
        answer_text="First cite KPI [DOC_KPI], then reference policy [DOC_POLICY].",
        citations=citations,
    )
    node = AnswerSynthesizerNode(composer=composer, cache_client=client)

    updates = await node(state)

    assert "DOC_KPI" not in updates["answer"]
    assert "DOC_POLICY" not in updates["answer"]
    assert "[2]" in updates["answer"]  # KPI maps to second citation even when first in text
    assert "[1]" in updates["answer"]
    inline = updates["answer_metadata"]["inline_citations"]
    assert any(entry["placeholder"] == "DOC_POLICY" and entry["footnote"] == 1 for entry in inline)
    assert any(entry["placeholder"] == "DOC_KPI" and entry["footnote"] == 2 for entry in inline)
    assert updates["citations"][0].metadata["citation_key"] == "c1"
    assert updates["citations"][1].metadata["citation_key"] == "c2"
