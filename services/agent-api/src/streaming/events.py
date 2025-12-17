"""SSE payload models for streaming chat responses."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SSEEventType(str, Enum):
    META = "meta"
    TASK_START = "task_start"
    TASK_END = "task_end"
    DONE = "done"
    TASK_ERROR = "task_error"


class SSEPayload(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)


class TaskLifecyclePayload(SSEPayload):
    node: str
    subgraph: str | None = None
    route: str | None = None
    sequence: int | None = None
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class TaskErrorPayload(SSEPayload):
    code: str
    message: str
    retryable: bool = False
    details: Mapping[str, Any] = Field(default_factory=dict)


PayloadType = TaskLifecyclePayload | TaskErrorPayload | SSEPayload


class SSEEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    event: SSEEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation_id: str
    task_id: str | None = None
    payload: PayloadType
    request_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _attach_conversation_from_payload(
        cls, data: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        if "conversation_id" not in data and isinstance(data.get("payload"), Mapping):
            payload_conversation_id = data["payload"].get("conversation_id")  # type: ignore[index]
            if payload_conversation_id:
                data["conversation_id"] = payload_conversation_id
        return data

    def as_dict(self) -> dict[str, Any]:
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
    return SSEEnvelope(
        event=event,
        conversation_id=conversation_id,
        payload=payload,
        task_id=task_id,
        request_id=request_id,
        timestamp=timestamp or datetime.now(UTC),
    )


EVENT_PAYLOAD_MODEL: dict[SSEEventType, type[PayloadType]] = {
    SSEEventType.TASK_START: TaskLifecyclePayload,
    SSEEventType.TASK_END: TaskLifecyclePayload,
    SSEEventType.DONE: SSEPayload,
    SSEEventType.TASK_ERROR: TaskErrorPayload,
}

__all__ = [
    "EVENT_PAYLOAD_MODEL",
    "PayloadType",
    "SSEEnvelope",
    "SSEEventType",
    "SSEPayload",
    "TaskErrorPayload",
    "TaskLifecyclePayload",
    "build_envelope",
]
