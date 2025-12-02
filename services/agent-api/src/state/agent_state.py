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
from typing import Any, Literal

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from cache.response_serializer import CacheCitation
from guardrails.models import GuardrailViolation, RouterRoute
from models.retrieval import AttachmentScope, NormalizedInput


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


class HitlTranscriptEntry(BaseModel):
    """Record describing a HITL pause/resume event for transcripts."""

    event: Literal["pause", "resume"] = Field(
        ..., description="Whether the entry marks a HITL pause or a resume event."
    )
    reason: str = Field(
        ..., description="HumanGate reason code (low_confidence, guardrail_violation)."
    )
    resume_token: str | None = Field(
        default=None,
        description="Resume token issued during the pause; echoed on resume for auditing.",
    )
    route: RouterRoute | None = Field(
        default=None,
        description="Route active when the HITL event occurred, if known.",
    )
    guardrail_codes: list[str] = Field(
        default_factory=list,
        description="Guardrail violation codes contributing to the pause (if any).",
    )
    confidence: float | None = Field(
        default=None,
        description="Router confidence captured when the pause decision was made.",
    )
    checkpoint_id: str | None = Field(
        default=None,
        description="Checkpoint identifier persisted for the pause/resume event.",
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
        description="When the HITL event was recorded (UTC).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata surfaced to transcripts/SSE.",
    )


class GraphEntitySummary(BaseModel):
    """Lightweight view of graph_entities rows (docs/data/schema_and_persistence.md §3.4)."""

    entity_id: str = Field(..., description="UUID referencing graph_entities.id.")
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
    labels: list[str] = Field(
        default_factory=list,
        description="Entity labels/tags leveraged for intent filtering.",
    )
    country_code: str | None = Field(
        default=None, description="Country partition used when generating the entity."
    )
    owner_user_id: str | None = Field(
        default=None,
        description="Owns user scope rows (None indicates base scope).",
    )
    hot_rank: int | None = Field(
        default=None, description="Rank based on graph_hot_entities view ordering."
    )


class GraphRelationSummary(BaseModel):
    """Edge + evidence rollup passed to downstream prompt builders."""

    relation_id: str = Field(..., description="graph_edges.id for determinism.")
    source_entity_id: str = Field(..., description="FK to the source entity id.")
    target_entity_id: str = Field(..., description="FK to the target entity id.")
    relation_type: str = Field(..., description="graph_edges.edge_type semantics.")
    directional: bool = Field(default=True, description="Whether the edge is directed.")
    weight: float | None = Field(
        default=None, description="Edge weighting used while ranking relations."
    )
    evidence_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk ids aggregated from graph_edge_evidence_rollup.",
    )
    evidence_count: int | None = Field(
        default=None,
        description="Number of evidence rows backing the relation.",
    )
    last_refreshed_at: datetime | None = Field(
        default=None,
        description="Timestamp recorded in graph_edge_evidence_rollup.last_refreshed_at.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional edge metadata when available."
    )


class GraphContext(BaseModel):
    """Graph + workflow context cached across LangGraph runs."""

    clusters: list[GraphEntitySummary] = Field(
        default_factory=list,
        description="Graph neighborhoods shipped between retrieval and subgraphs (docs/agents/implementation.md §3.2).",
    )
    relations: list[GraphRelationSummary] = Field(
        default_factory=list,
        description="Edge/evidence rollups derived from graph_edge_evidence_rollup (Task 04).",
    )
    workflow_plan_version: str | None = Field(
        default=None,
        description="Workflow graph version embedded in cache keys (docs/agents/implementation.md §3.2, docs/overview/system_architecture.md §3).",
    )
    algo_version: str | None = Field(
        default=None,
        description="Extraction/community detection algorithm version (docs/data/schema_and_persistence.md §3.4).",
    )
    scope_hash: str | None = Field(
        default=None,
        description="Hash of attachment scope ensuring GraphContext lines up with current documents.",
    )
    intent_tags: list[str] = Field(
        default_factory=list,
        description="Intent filters applied when gathering the graph view.",
    )
    fetched_at: datetime | None = Field(
        default=None, description="Timestamp when the graph payload was last hydrated."
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Computed expiry (fetched_at + TTL) used for refresh decisions.",
    )
    refresh_ttl_seconds: int | None = Field(
        default=None, description="TTL applied to the cached graph payload."
    )
    telemetry: dict[str, Any] = Field(
        default_factory=dict,
        description="Placeholder for retrieval metrics/telemetry emitted alongside the graph cache.",
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
    diff_summary: dict[str, Any] | None = Field(
        default=None,
        description="workflow_version_diffs projection or change_log for cache invalidation docs/epics/03.md Task 3.2.",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Flattened list of unique preconditions to surface plan-level dependencies.",
    )


class AnalystPlanStep(BaseModel):
    """Actionable analyst step derived from workflow plans."""

    key: str = Field(..., description="Stable identifier referencing the workflow node.")
    description: str = Field(..., description="Plain-language action for the analyst route.")
    required_context: list[str] = Field(
        default_factory=list,
        description="References to documents, graph clusters, or workflow prerequisites.",
    )
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Artifacts or answers the step should emit (tables, comparisons, summaries).",
    )
    workflow_ref: str | None = Field(
        default=None, description="Original workflow_plan step key for traceability."
    )


class AnalystPlan(BaseModel):
    """Structured plan produced by AnalystPlanner."""

    plan_id: str = Field(..., description="Workflow graph id anchoring the plan.")
    summary: str = Field(..., description="Short overview of the analysis strategy.")
    steps: list[AnalystPlanStep] = Field(
        default_factory=list, description="Ordered analyst steps used for synthesis."
    )
    complexity_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Normalized complexity score used for telemetry placeholders.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional plan metadata (prerequisites, plan_version, workflow diffs).",
    )


class ComparisonAttachment(BaseModel):
    """Attachment payload serialized by Analyst comparison responses."""

    attachment_type: Literal["text", "table", "chart", "workflow", "document"] = Field(
        ..., description="Semantic type used by the streaming API for rendering."
    )
    label: str = Field(..., description="Short user-facing description for the attachment.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data (tables, chart configs) streamed to clients.",
    )


class AnalystComparison(BaseModel):
    """Final analyst synthesis output containing attachments/highlights."""

    conclusion: str = Field(
        ..., description="Narrative conclusion referencing comparisons and plan context."
    )
    attachments: list[ComparisonAttachment] = Field(
        default_factory=list,
        description="Serialized attachments (tables/charts/workflow excerpts) for streaming.",
    )
    highlights: list[str] = Field(
        default_factory=list,
        description="Bullet summaries or key deltas surfaced alongside the answer.",
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


class GraphSummarySection(BaseModel):
    """Single deterministic block emitted by GraphSummarizer."""

    title: str = Field(..., description="Section heading (e.g., Entities, Relations).")
    body: str = Field(..., description="Plaintext content rendered into prompts.")
    tokens: int = Field(
        ge=0,
        description="Approximate token count for this section (Task 04 token budgeting).",
    )


class GraphSummary(BaseModel):
    """GraphSummarizer output consumed by downstream prompt builders."""

    headline: str = Field(
        ..., description="High-level summary for WorkflowPlanner/AnswerSynthesizer."
    )
    sections: list[GraphSummarySection] = Field(
        default_factory=list,
        description="Ordered prompt fragments with deterministic content ordering.",
    )
    total_tokens: int = Field(
        ge=0,
        description="Approximate total tokens consumed by the summary.",
    )
    budget_tokens: int = Field(
        ge=0,
        description="Configured max tokens allowed for the summary.",
    )
    fallback_used: bool = Field(
        default=False,
        description="Indicates whether the fallback/no-context summary was emitted.",
    )
    scope_hash: str | None = Field(
        default=None,
        description="Scope hash tied to this summary to keep cache alignment deterministic.",
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
    graph_summary: GraphSummary | None = Field(
        default=None,
        description="GraphSummarizer output used by WorkflowPlanner/AnswerSynthesizer (epic-03 Task 04).",
    )
    workflow_plan: WorkflowPlan | None = Field(
        default=None,
        description="WorkflowPlanner output reused by downstream subgraphs (docs/agents/implementation.md §3.2).",
    )
    analyst_plan: AnalystPlan | None = Field(
        default=None,
        description="Structured analyst plan derived from workflow_plan (Task 09).",
    )
    analyst_comparison: AnalystComparison | None = Field(
        default=None,
        description="Latest analyst comparison result including attachments (Task 09).",
    )
    cache_metadata: CacheMetadata = Field(
        default_factory=CacheMetadata,
        description="Valkey interaction metadata used for observability (docs/overview/system_architecture.md §3).",
    )
    answer: str | None = Field(
        default=None,
        description="Latest drafted answer text emitted by Informational/Analyst subgraphs.",
    )
    citations: list[CacheCitation] = Field(
        default_factory=list,
        description="Normalized citations tied to the current answer.",
    )
    answer_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk identifiers referenced by the answer/citations.",
    )
    answer_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Model metadata + telemetry captured during answer synthesis.",
    )
    quality_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence/quality estimate for the drafted answer.",
    )
    subgraph_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Placeholder for telemetry emitted by modality subgraphs prior to SSE wiring.",
    )
    route: RouterRoute | None = Field(
        default=None,
        description="Router decision emitted by Task 06 (docs/epics/03.md Task 3.3).",
    )
    route_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score attached to the router decision.",
    )
    next_subgraph: str | None = Field(
        default=None,
        description="Graph node identifier scheduled to run next (HumanGate when guardrails fail).",
    )
    router_reason: str | None = Field(
        default=None,
        description="Short explanation of the heuristic/intent used to classify the route.",
    )
    guardrail_findings: list[GuardrailViolation] = Field(
        default_factory=list,
        description="Structured guardrail violations/warnings surfaced to HumanGate (Task 06).",
    )
    guardrails_passed: bool = Field(
        default=True,
        description="Indicates whether blocking guardrail violations were found.",
    )
    retry_counter: int = Field(
        default=0,
        ge=0,
        description="Number of retry loops attempted within the current subgraph.",
    )
    error_log: list[str] = Field(
        default_factory=list,
        description="Chronological log of issues encountered during the run.",
    )
    hitl_transcript: list[HitlTranscriptEntry] = Field(
        default_factory=list,
        description="Chronological record of HITL pause/resume metadata for transcripts/SSE.",
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
    normalized_input: NormalizedInput | None = Field(
        default=None,
        description="Structured payload emitted by InputNormalizer (epic-03 Task 03).",
    )
    attachment_scope: AttachmentScope | None = Field(
        default=None,
        description="Hydrated documents/workflows from AttachmentScopeLoader (epic-03 Task 03).",
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
    "AnalystComparison",
    "AnalystPlan",
    "AnalystPlanStep",
    "AttachmentScope",
    "CacheMetadata",
    "ComparisonAttachment",
    "GraphContext",
    "GraphEntitySummary",
    "GraphRelationSummary",
    "GraphSummary",
    "GraphSummarySection",
    "GuardrailViolation",
    "HitlTranscriptEntry",
    "MessageSnapshot",
    "NormalizedInput",
    "RetrievalMetrics",
    "RouterRoute",
    "VisionFinding",
    "WorkflowPlan",
    "WorkflowPlanStep",
    "agent_state_from_persistence",
    "agent_state_to_persistence",
]
