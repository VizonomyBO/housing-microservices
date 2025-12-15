from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from models.retrieval import (
    AttachmentDocument,
    AttachmentScope,
    AttachmentWorkflow,
    NormalizedInput,
    TenantScope,
)
from nodes.retrieval.exceptions import WorkflowPlanningError
from nodes.retrieval.workflow_planner_node import WorkflowPlannerNode
from repositories.workflow_planner_repository import (
    WorkflowNodeSnapshot,
    WorkflowPlanSource,
)
from state.agent_state import AgentState, MessageSnapshot


class FakeWorkflowCatalog:
    def __init__(self, source: WorkflowPlanSource | None):
        self.source = source
        self.requested: list[str] = []

    async def fetch_plan_source(self, workflow_id: str):
        self.requested.append(workflow_id)
        return self.source


def _normalized_input() -> NormalizedInput:
    return NormalizedInput(
        normalized_prompt="plan",
        raw_prompt="plan",
        intent_tags=["route:informational"],
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[],
        scope_hash="scope-hash",
    )


def _attachment_scope(include_workflow: bool = True) -> AttachmentScope:
    workflows = []
    if include_workflow:
        workflows.append(
            AttachmentWorkflow(
                workflow_id="graph-1",
                name="Incident Response",
                domain="ops",
                version="v2",
                status="published",
            )
        )
    return AttachmentScope(
        documents=[
            AttachmentDocument(
                document_id="doc-1",
                canonical_name="Doc",
                access_scope="user_private",
                metadata={"content_hash": "hash-doc"},
            )
        ],
        workflows=workflows,
    )


def _agent_state(include_workflow: bool = True) -> AgentState:
    return AgentState(
        messages=[MessageSnapshot(message=HumanMessage(content="hi"))],
        conversation_id="conv-1",
        normalized_input=_normalized_input(),
        attachment_scope=_attachment_scope(include_workflow=include_workflow),
    )


def _plan_source(diff_summary: dict | None = None) -> WorkflowPlanSource:
    return WorkflowPlanSource(
        graph_id="graph-1",
        name="Incident Response",
        domain="ops",
        version="v2",
        country_code="USA",
        nodes=[
            WorkflowNodeSnapshot(
                key="coarse.1",
                path="coarse.1",
                description="Assess impact",
                preconditions={"country_code": "USA"},
                tool_hints=["graph"],
                artifacts={"prompt": "Assess impact"},
            ),
            WorkflowNodeSnapshot(
                key="mid.1",
                path="coarse.1.mid.1",
                description="Coordinate response",
                preconditions={"requires_doc": "doc-1"},
                tool_hints=[],
                artifacts={},
            ),
        ],
        diff_summary=diff_summary,
        change_log=None,
    )


@pytest.mark.asyncio
async def test_planner_builds_plan_and_cache_metadata() -> None:
    catalog = FakeWorkflowCatalog(_plan_source(diff_summary={"added_nodes": ["mid.1"]}))
    node = WorkflowPlannerNode(workflow_catalog=catalog)
    state = _agent_state()

    result = await node(state)

    workflow_plan = result["workflow_plan"]
    assert workflow_plan.plan_id == "graph-1"
    assert workflow_plan.diff_summary == {"added_nodes": ["mid.1"]}
    assert workflow_plan.prerequisites
    assert result["graph_context"].workflow_plan_version == "v2"
    assert result["cache_metadata"].cache_key.startswith("agent-api:retrieval:conv-1")


@pytest.mark.asyncio
async def test_planner_requires_workflow_scope() -> None:
    catalog = FakeWorkflowCatalog(_plan_source())
    node = WorkflowPlannerNode(workflow_catalog=catalog)
    state = _agent_state(include_workflow=False)

    with pytest.raises(WorkflowPlanningError):
        await node(state)


@pytest.mark.asyncio
async def test_planner_uses_change_log_when_diff_missing() -> None:
    plan_source = _plan_source(diff_summary=None)
    plan_source.change_log = {"removed_nodes": ["legacy"]}
    catalog = FakeWorkflowCatalog(plan_source)
    node = WorkflowPlannerNode(workflow_catalog=catalog)
    state = _agent_state()

    result = await node(state)

    assert result["workflow_plan"].diff_summary == {"removed_nodes": ["legacy"]}
