"""Conversation bootstrap helpers for the smoke workflow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from .clients import create_conversation
from .errors import SmokeError


class ConversationBootstrapper(Protocol):
    async def ensure_conversation(self, *, owner_user_id: str, country_code: str) -> str: ...


@dataclass(slots=True)
class HttpConversationBootstrapper:
    """Uses the public HTTP endpoint to create or reuse conversations."""

    client: httpx.AsyncClient
    token: str
    namespace: str = "reduced-e2e"
    tags: Sequence[str] = ("reduced_e2e", "demo")
    title: str | None = None

    async def ensure_conversation(self, *, owner_user_id: str, country_code: str) -> str:
        if not self.token:
            raise SmokeError("access token required for HTTP conversation bootstrap")
        _ = owner_user_id  # conversation owner derived from JWT subject
        payload = {
            "title": self.title or "Reduced E2E Smoke Session",
            "country_code": country_code,
            "namespace": self.namespace,
            "tags": list(self.tags),
        }
        result = await create_conversation(self.client, self.token, payload)
        return result.conversation_id


__all__ = [
    "ConversationBootstrapper",
    "HttpConversationBootstrapper",
]
