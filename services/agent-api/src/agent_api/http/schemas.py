"""HTTP-facing Pydantic schemas for the FastAPI gateway."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from models.retrieval import (
    ChatConstraints,
    ChatMessagePayload,
    ChatRequestContext,
    IncomingAttachment,
)


class ResponseMode(str, Enum):
    """Controls whether the HTTP response streams or blocks."""

    STREAM = "stream"
    BLOCKING = "blocking"


class ChatMessageBody(ChatMessagePayload):
    """Extends the retrieval ChatMessagePayload for HTTP inputs."""

    attachments: list[IncomingAttachment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_user_message(self) -> ChatMessageBody:
        if self.type != "user":
            raise ValueError("POST /v1/chat requires message.type='user'")
        return self


class ChatRequestBody(BaseModel):
    """Incoming request body for POST /v1/chat."""

    thread_id: str | None = Field(default=None, description="Existing thread identifier")
    session_id: str | None = Field(default=None, description="Logical session grouping id")
    message: ChatMessageBody
    hints: dict[str, Any] = Field(default_factory=dict)
    prompt_overrides: dict[str, Any] = Field(default_factory=dict)
    response_mode: ResponseMode | None = Field(
        default=None,
        description="Preferred response style (streaming vs blocking)",
    )
    stream: bool | None = Field(
        default=None,
        description="Legacy boolean alias for response_mode; true=stream",
    )
    constraints: ChatConstraints = Field(default_factory=ChatConstraints)

    def resolved_response_mode(self) -> ResponseMode:
        """Resolve the response mode, honoring the legacy stream flag."""

        if self.response_mode is not None:
            return self.response_mode
        if self.stream is not None:
            return ResponseMode.STREAM if self.stream else ResponseMode.BLOCKING
        return ResponseMode.STREAM

    def to_request_context(
        self,
        *,
        conversation_id: str,
        owner_user_id: str | None = None,
        workspace_id: str | None = None,
        tenant_id: str | None = None,
    ) -> ChatRequestContext:
        """Convert the HTTP payload into the internal ChatRequestContext."""

        message_payload = ChatMessagePayload.model_validate(self.message.model_dump())
        return ChatRequestContext(
            conversation_id=conversation_id,
            thread_id=conversation_id,
            session_id=self.session_id,
            message=message_payload,
            hints=dict(self.hints or {}),
            constraints=self.constraints,
            owner_user_id=owner_user_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )


class BlockingChatResponse(BaseModel):
    """JSON structure returned when clients opt out of streaming."""

    thread_id: str
    request_id: str
    done: dict[str, Any]
    messages: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "BlockingChatResponse",
    "ChatMessageBody",
    "ChatRequestBody",
    "ResponseMode",
]
