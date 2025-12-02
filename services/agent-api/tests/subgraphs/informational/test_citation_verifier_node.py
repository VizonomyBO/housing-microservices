from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from cache import CacheCitation
from hitl import HumanGateDecision
from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import AgentState, MessageSnapshot
from subgraphs.informational.citation_verifier_node import (
    CitationValidationContext,
    CitationValidationResult,
    CitationVerifierNode,
    HumanGateEvaluator,
)


class StubValidator:
    def __init__(self, *, is_valid: bool, message: str = "") -> None:
        self.is_valid = is_valid
        self.message = message or ("valid" if is_valid else "invalid")
        self.calls = 0

    async def validate(self, context: CitationValidationContext) -> CitationValidationResult:  # type: ignore[override]
        self.calls += 1
        return CitationValidationResult(
            is_valid=self.is_valid,
            invalid_citations=[CacheCitation(doc_id="doc-x", chunk_id="chunk-x")]
            if not self.is_valid
            else [],
            message=self.message,
        )


class StubHumanGate(HumanGateEvaluator):
    async def evaluate(
        self, state: AgentState, *, event_emitter=None  # type: ignore[override,unused-argument]
    ) -> HumanGateDecision:
        return HumanGateDecision(paused=True, state=state, reason=state.interrupt_reason)


def _state_with_answer() -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Explain",
        raw_prompt="Explain",
        tenant_scope=TenantScope(conversation_id="conv", thread_id="thr"),
        attachment_refs=[],
        scope_hash="scope",
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv",
        normalized_input=normalized,
        answer="draft",
        citations=[CacheCitation(doc_id="doc-1", chunk_id="chunk-1")],
    )


@pytest.mark.asyncio
async def test_valid_citations_no_op() -> None:
    state = _state_with_answer()
    validator = StubValidator(is_valid=True)
    node = CitationVerifierNode(validator=validator)

    updates = await node(state)

    assert validator.calls == 1
    assert updates["guardrails_passed"] is True


@pytest.mark.asyncio
async def test_invalid_citations_trigger_human_gate() -> None:
    state = _state_with_answer()
    validator = StubValidator(is_valid=False, message="bad citations")
    node = CitationVerifierNode(validator=validator, human_gate=StubHumanGate())

    updates = await node(state)

    assert updates["guardrails_passed"] is False
    assert updates["interrupt_reason"] == "invalid_citation"
    assert updates["next_subgraph"] == "human_gate"
    assert updates["guardrail_findings"][-1].code.value == "citation_mismatch"
