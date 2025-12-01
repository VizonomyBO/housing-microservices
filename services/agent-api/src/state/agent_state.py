"""Agent state models and serialization helpers.

This module defines the foundational AgentState schema referenced in:
- docs/agents/implementation.md §§3-5 (state buckets, LangGraph checkpoints, HITL)
- docs/overview/system_architecture.md §3 (cache + runtime topology)
- docs/data/schema_and_persistence.md §§3.6-3.8 (conversation + checkpoint tables)
- docs/epics/03.md Task 3.1 (AgentState expectations for Epic 3)
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


def _utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class MessageSnapshot(BaseModel):
    """Normalized wrapper around LangChain BaseMessage objects.

    Aligns with docs/agents/implementation.md §3.1 expectations that all
    conversation context is persisted as LangGraph-compatible messages.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    message: BaseMessage = Field(
        ..., description="LangChain message payload captured at checkpoint boundaries."
    )
    stored_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp mirroring messages.created_at (docs/data/schema_and_persistence.md §3.6).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Auxiliary metadata (token usage, node name) for telemetry stitching.",
    )

    @model_validator(mode="before")
    @classmethod
    def _deserialize_message(cls, value: Any) -> Any:
        """Convert serialized message dictionaries back into BaseMessage objects."""

        if isinstance(value, dict):
            maybe_message = value.get("message")
            if isinstance(maybe_message, BaseMessage):
                return value
            if isinstance(maybe_message, Mapping):
                hydrated = messages_from_dict([maybe_message])[0]
                new_value = dict(value)
                new_value["message"] = hydrated
                return new_value
        return value

    @model_serializer(mode="wrap")
    def _serialize(self, handler):  # type: ignore[override]
        data = handler(self)
        data["message"] = message_to_dict(self.message)
        return data


class GraphEntitySummary(BaseModel):
    """Lightweight view of graph_entities rows (docs/data/schema_and_persistence.md §3.9)."""

    entity_id: str = Field(..., description="UUID referencing graph_entities.id")
    label: str = Field(..., description="Human-friendly identifier surfaced to downstream nodes.")
    summary: str | None = Field(
        default=None,
        description="Short narrative per entity for downstream prompts (GraphSummarizer output).",
    )
    score: float | None = Field(
        default=None, description="Graph importance or retrieval score (0-1)."
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="Provenance documents that mentioned the entity (docs/agents/implementation.md §3.2).",
    )


class GraphContext(BaseModel):
    """Graph + workflow context cached across LangGraph runs."""

    clusters: list[GraphEntitySummary] = Field(
        default_factory=list,
        description="Graph neighborhoods shipped between retrieval and subgraphs (docs/agents/implementation.md §3.2).",
    )
    workflow_plan_version: str | None = Field(
        default=None,
        description="Workflow graph version embedded in cache keys (docs/agents/implementation.md §3.2, docs/overview/system_architecture.md §3).",
    )
    algo_version: str | None = Field(
        default=None,
        description="Extraction/community detection algorithm version (docs/data/schema_and_persistence.md §3.9).",
    )


class WorkflowPlanStep(BaseModel):
    """Single workflow node as described in docs/data/schema_and_persistence.md §3.10."""

    key: str = Field(..., description="workflow_nodes.node_key for deterministic replay.")
    description: str = Field(..., description="Human-readable action per workflow plan.")
    preconditions: dict[str, Any] = Field(
        default_factory=dict,
        description="State requirements before executing the step (docs/agents/implementation.md §3.2).",
    )
    tool_hints: list[str] = Field(
        default_factory=list,
        description="Tool suggestions (Polars, Vision) for downstream nodes (docs/agents/implementation.md §3.2).",
    )
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialized prompts/snippets referenced by the workflow step.",
    )


class WorkflowPlan(BaseModel):
    """Ordered workflow graph derived from WorkflowPlanner (docs/agents/implementation.md §3.2)."""

    plan_id: str = Field(..., description="workflow_graphs.id for traceability.")
    version: str | None = Field(
        default=None,
        description="workflow_versions.version referenced in cache keys (docs/data/schema_and_persistence.md §3.10).",
    )
    steps: list[WorkflowPlanStep] = Field(
        default_factory=list,
        description="Ordered list of actionable steps for subgraphs/HITL reviewers.",
    )


class CacheMetadata(BaseModel):
    """Metadata around cache lookups/writes (docs/overview/system_architecture.md §3)."""

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Versioned payload for cheap cache migrations (Task 01 requirement).",
    )
    cache_key: str | None = Field(
        default=None,
        description="Deterministic hash from InputNormalizer/WorkflowPlanner (docs/agents/implementation.md §3.3).",
    )
    hit: bool = Field(
        default=False,
        description="Indicates whether the current run short-circuited via cache (docs/agents/implementation.md §3.3).",
    )
    hit_at: datetime | None = Field(
        default=None, description="When the cache entry was read (if hit)."
    )
    written_at: datetime | None = Field(
        default=None,
        description="Timestamp when Guardrails wrote the entry back to Valkey.",
    )


class RetrievalMetrics(BaseModel):
    """Structured retrieval telemetry persisted with checkpoints (docs/agents/implementation.md §3.2)."""

    latency_ms: dict[str, float] = Field(
        default_factory=dict,
        description="Channel or phase keyed latency values (text/table/image/fusion/etc.).",
    )
    hybrid_k: int | None = Field(
        default=None,
        ge=0,
        description="Reciprocal Rank Fusion k parameter recorded for cache reproducibility.",
    )
    repairs: int = Field(
        default=0,
        ge=0,
        description="Count of retrieval repair loops triggered (docs/agents/implementation.md §3.2).",
    )
    schema_relaxations: int = Field(
        default=0,
        ge=0,
        description="Number of relaxed filters executed during retrieval (docs/agents/implementation.md §3.2).",
    )


class VisionFinding(BaseModel):
    """Vision analysis outputs that subgraphs hand back to Guardrails (docs/agents/implementation.md §3.2 Vision)."""

    chunk_id: str | None = Field(
        default=None,
        description="Optional FK to chunks.id for retrieved figure/caption evidence.",
    )
    figure_id: str | None = Field(
        default=None,
        description="External artifact identifier for the rendered figure (if available).",
    )
    summary: str = Field(
        ..., description="Short natural-language description of the visual finding."
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model confidence used by VisionVerifier/HumanGate.",
    )
    model: str | None = Field(
        default=None, description="Model used (e.g., gpt-5-mini) for auditability."
    )


class AgentState(BaseModel):
    """Primary LangGraph state object persisted via checkpoints (docs/epics/03.md Task 3.1)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    messages: list[MessageSnapshot] = Field(
        ...,
        description="Conversation context plus tool traces (docs/agents/implementation.md §3.1).",
    )
    graph_context: GraphContext = Field(
        default_factory=GraphContext,
        description="Graph neighborhoods/workflow versions cached between nodes (docs/agents/implementation.md §3.2).",
    )
    workflow_plan: WorkflowPlan | None = Field(
        default=None,
        description="WorkflowPlanner output reused by downstream subgraphs (docs/agents/implementation.md §3.2).",
    )
    cache_metadata: CacheMetadata = Field(
        default_factory=CacheMetadata,
        description="Valkey interaction metadata used for observability (docs/overview/system_architecture.md §3).",
    )
    retrieval_metrics: RetrievalMetrics = Field(
        default_factory=RetrievalMetrics,
        description="Hybrid retrieval telemetry forwarded via SSE metrics (docs/agents/implementation.md §3.2).",
    )
    vision_findings: list[VisionFinding] = Field(
        default_factory=list,
        description="Accumulated vision analysis claims per Vision subgraph (docs/agents/implementation.md §3.2 Vision).",
    )
    interrupt_reason: str | None = Field(
        default=None,
        description="HumanGate reason/HITL note when execution pauses (docs/agents/implementation.md §3.4).",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="agent_state_checkpoints.id for the persisted row (docs/data/schema_and_persistence.md §3.6).",
    )
    conversation_id: str = Field(
        ...,
        description="FK to conversations.id anchoring this state (docs/data/schema_and_persistence.md §3.6).",
    )
    created_at: datetime = Field(
        default_factory=_utc_now,
        description="When the checkpoint snapshot was created (docs/overview/system_architecture.md §3).",
    )

    @model_validator(mode="after")
    def _validate_messages(self) -> AgentState:
        if not self.messages:
            raise ValueError("AgentState requires at least one message snapshot.")
        return self


PersistencePayload = dict[str, Any]


# TODO(Task 02): Replace raw dict payloads with shared_data_layer DTOs once
# repositories wire up checkpoint persistence.


def agent_state_to_persistence(state: AgentState) -> PersistencePayload:
    """Serialize AgentState into a JSON-compatible payload for DB storage.

    Returns a dict suitable for agent_state_checkpoints.state JSON column. This helper
    centralizes LangChain message serialization so future schema updates (Task 02) only
    need to change one place.
    """

    return state.model_dump(mode="json")


def agent_state_from_persistence(payload: Mapping[str, Any]) -> AgentState:
    """Hydrate AgentState from repository payloads.

    Pydantic validation ensures malformed payloads raise a ValidationError, keeping
    checkpoint hydration safe without bespoke error handling.
    """

    return AgentState.model_validate(payload)


__all__ = [
    "AgentState",
    "CacheMetadata",
    "GraphContext",
    "GraphEntitySummary",
    "MessageSnapshot",
    "RetrievalMetrics",
    "VisionFinding",
    "WorkflowPlan",
    "WorkflowPlanStep",
    "agent_state_from_persistence",
    "agent_state_to_persistence",
]
