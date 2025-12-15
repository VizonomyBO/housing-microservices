from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import AttachmentDocument, AttachmentScope, NormalizedInput, TenantScope
from nodes.retrieval.graph.config import GraphRefreshSettings
from nodes.retrieval.graph.models import GraphEntityRecord, GraphRetrievalResult
from nodes.retrieval.graph_retriever_node import GraphRetrieverNode
from state.agent_state import AgentState, GraphContext, MessageSnapshot

DOC_ID = "11111111-1111-1111-1111-111111111111"


class StubGraphRepository:
    def __init__(self, result: GraphRetrievalResult):
        self.result = result
        self.filters = None
        self.called = False

    async def fetch_graph(self, *, filters, settings):
        self.called = True
        self.filters = filters
        return self.result


@pytest.mark.asyncio
async def test_retriever_filters_by_scope_and_documents():
    stub_repo = StubGraphRepository(
        GraphRetrievalResult(
            entities=[
                GraphEntityRecord(
                    entity_id="aaaa",
                    label="Housing Supply",
                    summary="Inventory is trending down",
                    score=0.92,
                    document_ids=[DOC_ID],
                    labels=["route:informational"],
                    country_code="USA",
                    owner_user_id=None,
                    hot_rank=1,
                    algo_version="v1",
                )
            ]
        )
    )
    node = GraphRetrieverNode(
        graph_repository=stub_repo,
        settings=GraphRefreshSettings(ttl_seconds=600, max_entities=5, max_relations=2),
        clock=lambda: datetime(2025, 12, 1, tzinfo=UTC),
    )
    state = _make_state(scope_hash="scope-1", intent_tags=["route:informational"])

    result = await node(state)

    assert "graph_context" in result
    graph_context = result["graph_context"]
    assert graph_context.scope_hash == "scope-1"
    assert graph_context.intent_tags == ["route:informational"]
    assert graph_context.clusters[0].label == "Housing Supply"
    assert stub_repo.called is True
    assert stub_repo.filters is not None
    assert stub_repo.filters.document_ids == [DOC_ID]
    assert stub_repo.filters.country_codes == ["USA"]


@pytest.mark.asyncio
async def test_retriever_reuses_cache_when_ttl_valid():
    stub_repo = StubGraphRepository(GraphRetrievalResult())
    node = GraphRetrieverNode(
        graph_repository=stub_repo,
        settings=GraphRefreshSettings(ttl_seconds=600),
        clock=lambda: datetime(2025, 12, 1, tzinfo=UTC),
    )
    cached_context = GraphContext(
        scope_hash="scope-1",
        intent_tags=["route:informational"],
        fetched_at=datetime(2025, 12, 1, tzinfo=UTC) - timedelta(minutes=5),
        expires_at=datetime(2025, 12, 1, tzinfo=UTC) + timedelta(minutes=5),
        refresh_ttl_seconds=600,
    )
    state = _make_state(
        scope_hash="scope-1", intent_tags=["route:informational"], graph_context=cached_context
    )

    result = await node(state)

    assert result == {}
    assert stub_repo.called is False


@pytest.mark.asyncio
async def test_retriever_force_refresh_bypasses_cache():
    stub_repo = StubGraphRepository(GraphRetrievalResult())
    node = GraphRetrieverNode(
        graph_repository=stub_repo,
        settings=GraphRefreshSettings(ttl_seconds=600),
        clock=lambda: datetime(2025, 12, 1, tzinfo=UTC),
        force_refresh=True,
    )
    cached_context = GraphContext(
        scope_hash="scope-1",
        intent_tags=["route:informational"],
        fetched_at=datetime(2025, 12, 1, tzinfo=UTC),
        expires_at=datetime(2025, 12, 1, tzinfo=UTC) + timedelta(minutes=10),
        refresh_ttl_seconds=600,
    )
    state = _make_state(
        scope_hash="scope-1", intent_tags=["route:informational"], graph_context=cached_context
    )

    await node(state)

    assert stub_repo.called is True


def _make_state(
    *,
    scope_hash: str,
    intent_tags: list[str],
    graph_context: GraphContext | None = None,
) -> AgentState:
    normalized_input = NormalizedInput(
        normalized_prompt="hi",
        raw_prompt="hi",
        tenant_scope=TenantScope(
            conversation_id="conv-1",
            thread_id="thr-1",
            country_code="USA",
        ),
        attachment_refs=[],
        scope_hash=scope_hash,
        intent_tags=intent_tags,
    )
    attachment_scope = AttachmentScope(
        documents=[
            AttachmentDocument(
                document_id=DOC_ID,
                canonical_name="Doc",
                access_scope="base",
                country_code="USA",
            )
        ]
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hello"))],
        conversation_id="conv-1",
        normalized_input=normalized_input,
        attachment_scope=attachment_scope,
        graph_context=graph_context or GraphContext(),
    )
