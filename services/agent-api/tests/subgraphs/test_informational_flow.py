from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from cache import CacheCitation, InMemoryValkeyClient
from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import AgentState, MessageSnapshot
from subgraphs.informational.answer_synthesizer_node import (
    AnswerSynthesisContext,
    AnswerSynthesisResult,
    AnswerSynthesizerNode,
)
from subgraphs.informational.citation_verifier_node import (
    CitationValidationContext,
    CitationValidationResult,
    CitationVerifierNode,
)


class FlowComposer:
    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult:  # type: ignore[override]
        return AnswerSynthesisResult(
            answer_text="Flow answer",
            citations=[CacheCitation(doc_id="doc-flow", chunk_id="chunk-flow")],
            chunk_ids=["chunk-flow"],
            quality_score=0.9,
            model_metadata={"model": "flow"},
        )


class FlowValidator:
    async def validate(self, context: CitationValidationContext) -> CitationValidationResult:  # type: ignore[override]
        return CitationValidationResult(is_valid=True)


def _base_state() -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Explain the new policy",
        raw_prompt="Explain the new policy",
        tenant_scope=TenantScope(conversation_id="conv-flow", thread_id="thr"),
        attachment_refs=[],
        scope_hash="scope",
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-flow",
        normalized_input=normalized,
    )


@pytest.mark.asyncio
async def test_informational_flow_happy_path() -> None:
    cache_client = InMemoryValkeyClient()
    synth_node = AnswerSynthesizerNode(composer=FlowComposer(), cache_client=cache_client)
    citation_node = CitationVerifierNode(validator=FlowValidator())
    state = _base_state()

    synth_updates = await synth_node(state)
    state = state.model_copy(update=synth_updates)
    citation_updates = await citation_node(state)
    final_state = state.model_copy(update=citation_updates)

    assert final_state.answer == "Flow answer"
    assert final_state.guardrails_passed is True
