"""CitationVerifier node for the Informational subgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cache.response_serializer import CacheCitation
from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from hitl.human_gate_service import HumanGateDecision
from state.agent_state import AgentState, GraphContext, WorkflowPlan


class CitationVerificationError(RuntimeError):
    """Raised when the citation verifier cannot proceed."""


@dataclass(slots=True)
class CitationValidationContext:
    """Inputs provided to the citation validator implementation."""

    answer: str
    citations: list[CacheCitation]
    graph_context: GraphContext
    workflow_plan: WorkflowPlan | None


@dataclass(slots=True)
class CitationValidationResult:
    """Validator output describing whether citations are trustworthy."""

    is_valid: bool
    invalid_citations: list[CacheCitation] = field(default_factory=list)
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class CitationValidatorProtocol(Protocol):
    """Interface that concrete citation validators must satisfy."""

    async def validate(self, context: CitationValidationContext) -> CitationValidationResult: ...


class HumanGateEvaluator(Protocol):
    """Subset of HumanGateService used by this node."""

    async def evaluate(self, state: AgentState) -> HumanGateDecision: ...


@dataclass(slots=True)
class CitationVerifierNode:
    """LangGraph node that marks invalid citations and routes to HITL when needed."""

    validator: CitationValidatorProtocol
    human_gate: HumanGateEvaluator | None = None
    interrupt_reason: str = "invalid_citation"

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        if not state.answer:
            raise CitationVerificationError("CitationVerifier requires an answer to inspect")
        context = CitationValidationContext(
            answer=state.answer,
            citations=list(state.citations),
            graph_context=state.graph_context,
            workflow_plan=state.workflow_plan,
        )
        verdict = await self.validator.validate(context)
        if verdict.is_valid:
            return {
                "guardrails_passed": True,
                "guardrail_findings": state.guardrail_findings,
            }
        return await self._handle_invalid_citations(state, verdict)

    async def _handle_invalid_citations(
        self, state: AgentState, verdict: CitationValidationResult
    ) -> dict[str, Any]:
        violation = GuardrailViolation(
            code=GuardrailCode.CITATION_MISMATCH,
            severity=GuardrailSeverity.ERROR,
            message=verdict.message or "Citations do not match retrieved evidence",
            details={
                "invalid_citations": [
                    citation.model_dump() for citation in verdict.invalid_citations
                ],
                **verdict.details,
            },
        )
        findings = list(state.guardrail_findings)
        findings.append(violation)
        error_log = list(state.error_log)
        error_log.append(violation.message)
        updates: dict[str, Any] = {
            "guardrail_findings": findings,
            "guardrails_passed": False,
            "error_log": error_log,
            "interrupt_reason": self.interrupt_reason,
            "next_subgraph": "human_gate",
        }
        annotated_state = state.model_copy(update=updates)
        if self.human_gate is None:
            return updates
        decision = await self.human_gate.evaluate(annotated_state)
        hitl_updates: dict[str, Any] = {
            "interrupt_reason": decision.state.interrupt_reason,
            "hitl_transcript": decision.state.hitl_transcript,
        }
        if decision.paused:
            hitl_updates["checkpoint_id"] = decision.state.checkpoint_id
        return {**updates, **hitl_updates}


__all__ = [
    "CitationValidationContext",
    "CitationValidationResult",
    "CitationValidatorProtocol",
    "CitationVerificationError",
    "CitationVerifierNode",
    "HumanGateEvaluator",
]
