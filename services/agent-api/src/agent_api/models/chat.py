"""Internal chat request models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_api.http.schemas import ChatConstraints, ChatMessagePayload


@dataclass(slots=True)
class ChatRequestContext:
    conversation_id: str
    thread_id: str
    session_id: str | None
    allow_stateless: bool
    message: ChatMessagePayload
    hints: dict[str, Any]
    constraints: ChatConstraints
    owner_user_id: str | None = None
    workspace_id: str | None = None
    tenant_id: str | None = None


__all__ = ["ChatRequestContext"]
