"""Pydantic models describing the SSE contract for LangGraph events.

These models mirror the envelopes documented in docs/interfaces/api_contracts.md §3 and
Task 3.5 of docs/epics/03.md so every streaming payload is validated before it reaches
clients.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SSEEventType(str, Enum):
    """Enumerates all supported SSE event categories."""

    META = "meta"
    TASK_START = "task_start"
    TASK_END = "task_end"
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_WRITE = "cache_write"
    HITL_PAUSE = "hitl_pause"
    HITL_RESUME = "hitl_resume"
    TELEMETRY_SNAPSHOT = "telemetry_snapshot"
    DONE = "done"
    TASK_ERROR = "task_error"
    DEMO_MODE_SKIPPED = "demo_mode_skipped"


class SSEPayload(BaseModel):
    """Base payload that allows forward-compatible fields."""

    model_config = ConfigDict(extra="allow", frozen=True)


class TaskLifecyclePayload(SSEPayload):
    """Metadata describing LangGraph node/subgraph execution."""

    node: str = Field(..., description="Canonical LangGraph node identifier")
    subgraph: str | None = Field(
        default=None, description="Optional subgraph grouping for the node."
    )
    route: str | None = Field(default=None, description="Resolved Router route when applicable.")
    sequence: int | None = Field(
        default=None, description="Monotonic counter for ordering within a run."
    )
    metadata: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Additional structured attributes surfaced to observability clients.",
    )


class CacheEventPayload(SSEPayload):
    """Cache-related telemetry referencing the shared CacheWriter schema."""

    cache_key: str = Field(..., description="Fully-qualified cache key.")
    namespace: str | None = Field(default=None, description="Cache namespace/prefix.")
    hit: bool | None = Field(
        default=None,
        description="Whether the cache lookup was a hit (true) or miss (false).",
    )
    source: str | None = Field(
        default=None,
        description="Physical cache store that served the response (e.g., valkey).",
    )
    latency_ms: float | None = Field(
        default=None, description="Latency in milliseconds for the cache operation."
    )
    ttl_seconds: int | None = Field(
        default=None,
        description="Configured TTL for writes so clients can reason about freshness.",
    )
    payload_hash: str | None = Field(
        default=None, description="Hash/fingerprint of the cached payload."
    )
    metadata: Mapping[str, Any] = Field(
        default_factory=dict, description="Miscellaneous cache telemetry."
    )
    metric_refs: list[str] = Field(
        default_factory=list,
        description="Prometheus metric names associated with this cache event.",
    )


class HitlEventPayload(SSEPayload):
    """Payload schema for human-in-the-loop pause/resume events."""

    conversation_id: str = Field(..., description="Conversation identifier.")
    checkpoint_id: str = Field(..., description="Checkpoint representing paused state.")
    resume_token: str | None = Field(
        default=None,
        description="Token clients must echo back to resume the paused run.",
    )
    reason: str | None = Field(default=None, description="Reason for pause/resume.")
    route: str | None = Field(default=None, description="Route active when the event fired.")
    confidence: float | None = Field(
        default=None, description="Router confidence at the time of the event."
    )
    guardrail_codes: list[str] = Field(
        default_factory=list,
        description="Blocking guardrail codes contributing to the pause.",
    )
    metadata: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary annotations (e.g., operator id, resume status).",
    )
    metric_refs: list[str] = Field(
        default_factory=list,
        description="Prometheus metric names that track this HITL event.",
    )


class TelemetrySnapshotPayload(SSEPayload):
    """Generic metrics payload for cache ratios, token usage, etc."""

    metrics: Mapping[str, Any] = Field(
        default_factory=dict, description="Metric name/value mappings."
    )
    labels: Mapping[str, str] = Field(
        default_factory=dict, description="Dimensional labels for the metrics."
    )
    window_ms: int | None = Field(default=None, description="Measurement window in milliseconds.")


class TaskErrorPayload(SSEPayload):
    """Payload emitted when the gateway surfaces an unexpected error."""

    code: str = Field(..., description="Application-level error code (e.g., INTERNAL_ERROR).")
    message: str = Field(..., description="Human-readable explanation of the failure.")
    retryable: bool = Field(default=False, description="Whether clients may safely retry.")
    details: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Optional structured metadata (stack hashes, node info, etc.).",
    )


PayloadType = (
    TaskLifecyclePayload
    | CacheEventPayload
    | HitlEventPayload
    | TelemetrySnapshotPayload
    | TaskErrorPayload
    | SSEPayload
)


class SSEEnvelope(BaseModel):
    """Canonical envelope frames every SSE event."""

    model_config = ConfigDict(frozen=True)

    event: SSEEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation_id: str = Field(..., description="Conversation identifier (thread id).")
    task_id: str | None = Field(
        default=None,
        description="Optional task/run identifier so clients can correlate branches.",
    )
    payload: PayloadType
    request_id: str | None = Field(
        default=None,
        description="Gateway Viz-Request-Id for trace correlation.",
    )

    @model_validator(mode="before")
    @classmethod
    def _attach_conversation_from_payload(
        cls, data: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        """Allow HITL payloads that already contain conversation ids to drive the envelope."""

        if "conversation_id" not in data and isinstance(data.get("payload"), Mapping):
            payload_conversation_id = data["payload"].get("conversation_id")  # type: ignore[index]
            if payload_conversation_id:
                data["conversation_id"] = payload_conversation_id
        return data

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the envelope."""

        return self.model_dump(mode="json")


def build_envelope(
    *,
    event: SSEEventType,
    conversation_id: str,
    payload: PayloadType,
    task_id: str | None = None,
    request_id: str | None = None,
    timestamp: datetime | None = None,
) -> SSEEnvelope:
    """Factory helper to keep call sites concise."""

    return SSEEnvelope(
        event=event,
        conversation_id=conversation_id,
        task_id=task_id,
        payload=payload,
        request_id=request_id,
        timestamp=timestamp or datetime.now(UTC),
    )

class DemoModePayload(SSEPayload):
    """Payload describing capabilities skipped while demo mode is active."""

    capability: str = Field(
        ..., description="Capability that was suppressed (vision, numerical, etc.)"
    )
    reason: str = Field(
        default="reduced_scope",
        description="Reason code describing why the capability was disabled.",
    )
    metadata: Mapping[str, Any] = Field(
        default_factory=dict,
        description="Structured metadata (allowed chunk types, text-only flags, etc.).",
    )


EVENT_PAYLOAD_MODEL: dict[SSEEventType, type[SSEPayload]] = {
    SSEEventType.TASK_START: TaskLifecyclePayload,
    SSEEventType.TASK_END: TaskLifecyclePayload,
    SSEEventType.CACHE_HIT: CacheEventPayload,
    SSEEventType.CACHE_MISS: CacheEventPayload,
    SSEEventType.CACHE_WRITE: CacheEventPayload,
    SSEEventType.HITL_PAUSE: HitlEventPayload,
    SSEEventType.HITL_RESUME: HitlEventPayload,
    SSEEventType.TELEMETRY_SNAPSHOT: TelemetrySnapshotPayload,
    SSEEventType.META: SSEPayload,
    SSEEventType.DONE: SSEPayload,
    SSEEventType.TASK_ERROR: TaskErrorPayload,
    SSEEventType.DEMO_MODE_SKIPPED: DemoModePayload,
}
