"""Request-scoped context objects shared across dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RequestContext:
    """Correlation metadata extracted from the HTTP layer."""

    request_id: str
    traceparent: str | None = None
    idempotency_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AuthContext:
    """Authenticated user context shared across FastAPI dependencies."""

    user_id: str | None
    tenant_id: str | None = None
    roles: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["AuthContext", "RequestContext"]
