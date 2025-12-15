from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import NormalizedInput, TenantScope
from state.agent_state import (
    AgentState,
    MessageSnapshot,
    WorkflowPlan,
    WorkflowPlanStep,
)
from subgraphs.analyst.analyst_planner_node import AnalystPlannerNode


def _base_state() -> AgentState:
    normalized = NormalizedInput(
        normalized_prompt="Compare Liberia and Ghana",
        raw_prompt="Compare Liberia and Ghana",
        tenant_scope=TenantScope(conversation_id="conv-analyst", thread_id="thr"),
        attachment_refs=[],
        scope_hash="scope",
    )
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-analyst",
        normalized_input=normalized,
    )


@pytest.mark.asyncio
async def test_builds_plan_and_metrics() -> None:
    workflow_plan = WorkflowPlan(
        plan_id="wf-analyst",
        version="v1",
        steps=[
            WorkflowPlanStep(
                key="analyst.1",
                description="Gather macro indicators",
                preconditions={"doc": "doc_a"},
                artifacts={"snippet": "..."},
            ),
            WorkflowPlanStep(
                key="analyst.2",
                description="Compare fiscal outcomes",
                preconditions={"doc": "doc_b"},
                artifacts={},
            ),
        ],
        prerequisites=["country:LBR"],
    )
    state = _base_state().model_copy(update={"workflow_plan": workflow_plan})
    node = AnalystPlannerNode()

    updates = await node(state)

    plan = updates["analyst_plan"]
    assert plan.plan_id == "wf-analyst"
    assert len(plan.steps) == 2
    assert plan.complexity_score is not None
    assert plan.complexity_score > 0
    metrics = updates["subgraph_metrics"]
    assert metrics["analyst.plan.steps"] == 2
