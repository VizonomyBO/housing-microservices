"""Request-scoped context objects."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_api.auth.validator import AuthContext


@dataclass(slots=True)
class RequestContext:
    request_id: str
    traceparent: str | None = None
    idempotency_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


__all__ = ["AuthContext", "RequestContext"]
