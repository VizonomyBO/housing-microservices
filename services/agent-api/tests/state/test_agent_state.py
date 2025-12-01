"""Unit tests for the AgentState schema and helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from models.retrieval import (
    AttachmentDocument,
    AttachmentReference,
    AttachmentScope,
    AttachmentType,
    NormalizedInput,
    TenantScope,
)
from state.agent_state import (
    AgentState,
    CacheMetadata,
    GraphContext,
    GraphEntitySummary,
    MessageSnapshot,
    RetrievalMetrics,
    VisionFinding,
    WorkflowPlan,
    WorkflowPlanStep,
    agent_state_from_persistence,
    agent_state_to_persistence,
)


def _sample_snapshot(content: str = "hello") -> MessageSnapshot:
    return MessageSnapshot(message=HumanMessage(content=content))


def test_agent_state_instantiation_minimum() -> None:
    snapshot = _sample_snapshot()
    state = AgentState(
        messages=[snapshot],
        conversation_id="conv-001",
        created_at=datetime.now(UTC),
    )

    assert state.messages[0].message.content == "hello"
    assert state.cache_metadata.schema_version == 1
    assert state.graph_context.clusters == []


def test_agent_state_requires_at_least_one_message() -> None:
    with pytest.raises(ValueError, match="at least one message"):
        AgentState(messages=[], conversation_id="conv-002", created_at=datetime.now(UTC))


def test_agent_state_round_trip_serialization() -> None:
    snapshot = _sample_snapshot("ready to plan")
    state = AgentState(
        messages=[snapshot],
        graph_context=GraphContext(
            clusters=[
                GraphEntitySummary(
                    entity_id="entity-123",
                    label="GDP",
                    summary="GDP entity",
                    score=0.9,
                    document_ids=["doc-1"],
                )
            ],
            workflow_plan_version="workflow-v1",
            algo_version="algo-2024.10",
        ),
        workflow_plan=WorkflowPlan(
            plan_id="plan-123",
            version="v1",
            steps=[
                WorkflowPlanStep(
                    key="coarse.1",
                    description="Gather baseline context",
                    preconditions={"country_code": "USA"},
                    tool_hints=["RAGTool"],
                )
            ],
            diff_summary={"added_nodes": ["coarse.1"]},
            prerequisites=['country_code:"USA"'],
        ),
        cache_metadata=CacheMetadata(schema_version=1, cache_key="cache-abc", hit=True),
        retrieval_metrics=RetrievalMetrics(
            latency_ms={"text": 120.5},
            hybrid_k=60,
            repairs=1,
            schema_relaxations=0,
        ),
        vision_findings=[
            VisionFinding(
                chunk_id="chunk-1",
                figure_id="figure-7",
                summary="Identified chart trend",
                confidence=0.82,
                model="gpt-5-mini",
            )
        ],
        interrupt_reason="HITL clarification",
        checkpoint_id="chkpt-123",
        conversation_id="conv-003",
        normalized_input=NormalizedInput(
            normalized_prompt="ready to plan",
            raw_prompt=" ready to plan  ",
            language_code="en",
            language_confidence=0.98,
            intent_tags=["route:informational"],
            tenant_scope=TenantScope(
                conversation_id="conv-003",
                thread_id="thr-003",
                session_id="sess-1",
                owner_user_id="user-1",
                workspace_id="ws-9",
                tenant_id="tenant-22",
                country_code="USA",
            ),
            attachment_refs=[
                AttachmentReference(
                    asset_type=AttachmentType.DOCUMENT,
                    asset_id="doc-1",
                    attach_source="user_upload",
                    canonical_name="Scope Doc",
                    access_scope="user_private",
                    visibility="visible",
                    read_only=False,
                    provided_in_request=True,
                )
            ],
            scope_hash="hash-abc",
            warnings=["trimmed whitespace"],
        ),
        attachment_scope=AttachmentScope(
            documents=[
                AttachmentDocument(
                    document_id="doc-1",
                    canonical_name="Scope Doc",
                    access_scope="user_private",
                    language="en",
                    country_code="USA",
                    tags=["finance"],
                    auto_attached=False,
                )
            ]
        ),
        created_at=datetime(2025, 12, 1, tzinfo=UTC),
    )

    payload = agent_state_to_persistence(state)
    rehydrated = agent_state_from_persistence(payload)

    assert rehydrated.conversation_id == state.conversation_id
    assert rehydrated.messages[0].message.content == "ready to plan"
    assert rehydrated.workflow_plan is not None
    assert rehydrated.workflow_plan.steps[0].key == "coarse.1"
    assert rehydrated.workflow_plan.diff_summary == {"added_nodes": ["coarse.1"]}
    assert rehydrated.workflow_plan.prerequisites == ['country_code:"USA"']
    assert rehydrated.created_at == state.created_at
    assert rehydrated.cache_metadata.hit is True
    assert rehydrated.normalized_input is not None
    assert rehydrated.normalized_input.scope_hash == "hash-abc"
    assert rehydrated.attachment_scope is not None
    assert rehydrated.attachment_scope.documents[0].document_id == "doc-1"


def test_agent_state_from_persistence_validates_required_fields() -> None:
    snapshot = _sample_snapshot("fallback")
    state = AgentState(
        messages=[snapshot],
        conversation_id="conv-004",
        created_at=datetime.now(UTC),
    )
    payload = agent_state_to_persistence(state)
    payload_without_conversation = {k: v for k, v in payload.items() if k != "conversation_id"}

    with pytest.raises(ValidationError):
        agent_state_from_persistence(payload_without_conversation)


def test_message_snapshot_serialization_preserves_langchain_types() -> None:
    ai_message = AIMessage(content="Answer")
    snapshot = MessageSnapshot(message=ai_message)
    serialized = snapshot.model_dump(mode="json")
    assert serialized["message"]["type"] == "ai"

    restored = MessageSnapshot.model_validate(serialized)
    assert isinstance(restored.message, AIMessage)
    assert restored.message.content == "Answer"
