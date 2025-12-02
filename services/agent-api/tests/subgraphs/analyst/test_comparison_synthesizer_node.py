from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from cache import CacheCitation, CacheWriter, InMemoryValkeyClient
from cache.response_serializer import CacheWorkflowPlanExcerpt
from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import (
    AgentState,
    AnalystPlan,
    AnalystPlanStep,
    CacheMetadata,
    ComparisonAttachment,
    MessageSnapshot,
)
from subgraphs.analyst.comparison_synthesizer_node import (
    ComparisonResponseBuilder,
    ComparisonSynthesisContext,
    ComparisonSynthesisResult,
    ComparisonSynthesizerNode,
)


class StubBuilder(ComparisonResponseBuilder):
    def __init__(self) -> None:
        self.calls = 0

    async def build(self, context: ComparisonSynthesisContext) -> ComparisonSynthesisResult:  # type: ignore[override]
        self.calls += 1
        return ComparisonSynthesisResult(
            answer_text="Final analyst answer",
            citations=[CacheCitation(doc_id="doc-a", chunk_id="chunk-z")],
            attachments=[
                ComparisonAttachment(attachment_type="table", label="Delta", payload={"rows": []})
            ],
            chunk_ids=["chunk-z"],
            quality_score=0.95,
            model_metadata={"model": "stub"},
            workflow_excerpt=CacheWorkflowPlanExcerpt(
                plan_id="wf", version="v1", steps=["step"], summary="s"
            ),
        )


def _state_with_plan(cache_metadata: CacheMetadata | None = None) -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Compare countries",
        raw_prompt="Compare countries",
        tenant_scope=TenantScope(conversation_id="conv", thread_id="thr"),
        attachment_refs=[],
        scope_hash="scope",
    )
    plan = AnalystPlan(
        plan_id="wf",
        summary="Plan",
        steps=[
            AnalystPlanStep(
                key="step.1",
                description="Gather context",
                required_context=["doc:1"],
                expected_outputs=["table"],
                workflow_ref="step.1",
            )
        ],
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv",
        normalized_input=normalized,
        analyst_plan=plan,
        cache_metadata=cache_metadata or CacheMetadata(cache_key="agent-api:retrieval:conv"),
    )


@pytest.mark.asyncio
async def test_comparison_synthesizer_streams_and_writes_cache() -> None:
    client = InMemoryValkeyClient()
    writer = CacheWriter(client=client)
    state = _state_with_plan()
    node = ComparisonSynthesizerNode(builder=StubBuilder(), cache_writer=writer)

    updates = await node(state)

    assert updates["answer"] == "Final analyst answer"
    assert updates["quality_score"] == pytest.approx(0.95)
    assert updates["analyst_comparison"].attachments[0].label == "Delta"
    cache_key = state.cache_metadata.cache_key
    assert cache_key is not None
    stored = await client.get(cache_key)
    assert stored is not None
