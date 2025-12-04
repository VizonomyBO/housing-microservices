from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agent_api.reduced_scope import ReducedScopeFlags
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
    prompt: str,
    *,
    intent_tags: list[str] | None = None,
    workflow_plan: WorkflowPlan | None = None,
    reduced_scope_flags: ReducedScopeFlags | None = None,
) -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt=prompt,
        raw_prompt=prompt,
        tenant_scope=TenantScope(conversation_id="conv", thread_id="thr", country_code="USA"),
        attachment_refs=[],
        scope_hash="abc",
        intent_tags=intent_tags or [],
        reduced_scope_flags=reduced_scope_flags or ReducedScopeFlags(),
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
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_vision_keywords_detected():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Describe the attached image and screenshot", intent_tags=[])

    result = await router(state)

    assert result["route"] == RouterRoute.VISION
    assert result["router_reason"] == "vision_signal"


@pytest.mark.asyncio
async def test_compare_keywords_force_numerical_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Draft a strategy plan that compares two programs")

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_strategy_plan_without_compare_routes_to_analyst():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Draft a strategy plan for District 9 partners")

    result = await router(state)

    assert result["route"] == RouterRoute.ANALYST


@pytest.mark.asyncio
async def test_default_to_informational_when_no_signal():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    state = _agent_state("Hello there")

    result = await router(state)

    assert result["route"] == RouterRoute.INFORMATIONAL
    assert result["router_reason"] == "default"
    assert result["requires_sql"] is False


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


@pytest.mark.asyncio
async def test_kpi_question_triggers_numerical_path_without_hints():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = (
        "Using the KPI dashboard and utilization table, identify who exceeds the 80 percent trigger "
        "and summarize the plan."
    )
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["router_reason"] == "numerical_signal"
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_guardrail_policy_with_numbers_routes_to_numerical():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = (
        "How should we pair the voucher guardrails with arrears relief when scores exceed 80 "
        "and renters owe 1,200 dollars?"
    )
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_simple_addition_forces_numerical_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = "What is 40 + 2 from the KPI memo table?"
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True
    assert result["router_reason"] == "numerical_signal"


@pytest.mark.asyncio
async def test_percentage_comparison_triggers_numerical_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = "Which city exceeds the 80 percent KPI threshold?"
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_reduced_scope_flags_do_not_skip_numerical_route():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    flags = ReducedScopeFlags(enabled=True, text_only_chunks=True, emit_demo_events=False)
    state = _agent_state("Add the two KPI rows", reduced_scope_flags=flags)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True


@pytest.mark.asyncio
async def test_percentage_thresholds_require_sql_path():
    router = RouterNode(guardrail_engine=StubGuardrailEngine())
    prompt = "Which city exceeds 80 percent utilization this quarter?"
    state = _agent_state(prompt)

    result = await router(state)

    assert result["route"] == RouterRoute.NUMERICAL
    assert result["requires_sql"] is True
    assert result["router_reason"] == "numerical_signal"
