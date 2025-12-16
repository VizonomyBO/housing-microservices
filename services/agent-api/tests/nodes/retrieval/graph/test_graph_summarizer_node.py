from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage

from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.graph.config import GraphSummarySettings
from nodes.retrieval.graph_summarizer_node import GraphSummarizerNode
from state.agent_state import (
    AgentState,
    GraphContext,
    GraphEntitySummary,
    GraphRelationSummary,
    GraphSummary,
    MessageSnapshot,
)


@pytest.mark.asyncio
async def test_summarizer_builds_deterministic_sections():
    graph_context = GraphContext(
        clusters=[
            GraphEntitySummary(
                entity_id="a",
                label="Entity A",
                summary="Summary A",
                score=0.9,
                document_ids=["doc-1"],
            ),
            GraphEntitySummary(
                entity_id="b",
                label="Entity B",
                summary="Summary B",
                score=0.3,
                document_ids=["doc-2"],
            ),
        ],
        relations=[
            GraphRelationSummary(
                relation_id="rel-1",
                source_entity_id="a",
                target_entity_id="b",
                relation_type="influences",
                directional=True,
                weight=0.7,
                evidence_chunk_ids=["chunk-1"],
                last_refreshed_at=datetime(2025, 12, 1, tzinfo=UTC),
            )
        ],
        scope_hash="scope-1",
    )
    state = _make_state(graph_context)
    node = GraphSummarizerNode()

    result = await node(state)

    summary: GraphSummary = result["graph_summary"]
    assert summary.headline == "2 entities linked via 1 relations"
    assert [section.title for section in summary.sections] == ["Key entities", "Key relations"]
    assert "Entity A" in summary.sections[0].body.splitlines()[0]


@pytest.mark.asyncio
async def test_summarizer_respects_token_budget():
    graph_context = GraphContext(
        clusters=[
            GraphEntitySummary(
                entity_id="a",
                label="Entity A",
                summary="Summary A",
                score=0.9,
                document_ids=["doc-1"],
            ),
            GraphEntitySummary(
                entity_id="b",
                label="Entity B",
                summary="Summary B",
                score=0.8,
                document_ids=["doc-2"],
            ),
        ],
        relations=[],
        scope_hash="scope-1",
    )
    state = _make_state(graph_context)
    node = GraphSummarizerNode(
        settings=GraphSummarySettings(
            max_total_tokens=30, max_entity_tokens=15, max_relation_tokens=5
        )
    )

    result = await node(state)

    summary: GraphSummary = result["graph_summary"]
    # Only the first entity should appear due to the strict token budget.
    assert summary.sections[0].body.count("\n") == 0


@pytest.mark.asyncio
async def test_summarizer_fallback_when_empty_context():
    graph_context = GraphContext()
    state = _make_state(graph_context)
    node = GraphSummarizerNode()

    with pytest.raises(NodeError):
        await node(state)


def _make_state(graph_context: GraphContext) -> AgentState:
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hello"))],
        conversation_id="conv-1",
        graph_context=graph_context,
    )
