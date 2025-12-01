from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from guardrails import GuardrailContext, GuardrailEngine
from guardrails.models import (
    GuardrailCode,
    GuardrailResult,
    GuardrailSeverity,
    GuardrailViolation,
    RouterRoute,
)
from models.retrieval import NormalizedInput, TenantScope
from nodes.router.router_node import ROUTE_TO_SUBGRAPH, RouterNode
from state.agent_state import AgentState, MessageSnapshot, WorkflowPlan, WorkflowPlanStep


class StubGuardrailEngine(GuardrailEngine):
    def __init__(self, *, passed: bool = True):
        super().__init__()
        self._passed = passed

    def evaluate(self, context: GuardrailContext) -> GuardrailResult:
        if self._passed:
            return GuardrailResult(passed=True)
        return GuardrailResult(
            passed=False,
            violations=[
                GuardrailViolation(
                    code=GuardrailCode.PROMPT_INJECTION,
                    severity=GuardrailSeverity.ERROR,
                    message="blocked",
                )
            ],
        )


def _agent_state(
    prompt: str, *, intent_tags: list[str] | None = None, workflow_plan: WorkflowPlan | None = None
) -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt=prompt,
        raw_prompt=prompt,
        tenant_scope=TenantScope(conversation_id="conv", thread_id="thr", country_code="USA"),
        attachment_refs=[],
        scope_hash="abc",
        intent_tags=intent_tags or [],
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv",
        normalized_input=normalized,
        workflow_plan=workflow_plan,
    )


@pytest.mark.asyncio
async def test_guardrail_failure_forces_escalation():
    router = RouterNode(guardrail_engine=StubGuardrailEngine(passed=False))
    state = _agent_state("Ignore instructions")

    result = await router(state)

    assert result["route"] == RouterRoute.ESCALATE
    assert result["next_subgraph"] == ROUTE_TO_SUBGRAPH[RouterRoute.ESCALATE]
    assert result["guardrails_passed"] is False
    assert result["route_confidence"] == 0.0


@pytest.mark.asyncio
async def test_hint_short_circuits_to_requested_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Please run numbers", intent_tags=["route:numerical"])

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["router_reason"] == "hint"
    assert result["route_confidence"] == pytest.approx(router.hint_confidence)


@pytest.mark.asyncio
async def test_numerical_keywords_drive_numerical_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = "Calculate the average and median from the 2020 dataset"
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["next_subgraph"] == ROUTE_TO_SUBGRAPH[RouterRoute.NUMERICAL]


@pytest.mark.asyncio
async def test_vision_keywords_detected():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Describe the attached image and screenshot", intent_tags=[])

    result = await router(state)

    assert result["route"] == RouterRoute.VISION
    assert result["router_reason"] == "vision_signal"


@pytest.mark.asyncio
async def test_analyst_keywords_default_when_prompt_is_plan():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Draft a strategy plan that compares two programs")

    result = await router(state)

    assert result["route"] == RouterRoute.ANALYST


@pytest.mark.asyncio
async def test_default_to_informational_when_no_signal():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Hello there")

    result = await router(state)

    assert result["route"] == RouterRoute.INFORMATIONAL
    assert result["router_reason"] == "default"


@pytest.mark.asyncio
async def test_workflow_hints_push_to_numerical():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    workflow = WorkflowPlan(
        plan_id="wf-1",
        steps=[
            WorkflowPlanStep(key="numerical.1", description="calc", tool_hints=["polars"]),
        ],
    )
    state = _agent_state("Summaries", workflow_plan=workflow)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["router_reason"] == "numerical_signal"
