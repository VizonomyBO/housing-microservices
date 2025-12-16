"""Rate limiter protocols for the HTTP gateway (fail-fast by default)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class RateLimiterProtocol(Protocol):
    """Interface implemented by gateway-level rate limiter adapters."""

    async def acquire(
        self,
        *,
        bucket: str,
        tokens: int,
        route: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Reserve permits for the provided bucket (no-op for demos)."""

    def response_headers(self) -> dict[str, str]:
        """Return headers describing the active limiter policy."""

    def sse_metadata(self) -> dict[str, Any]:
        """Expose metadata surfaced to SSE/meta events."""


@dataclass(slots=True)
class NullRateLimiter(RateLimiterProtocol):
    """Limiter that performs no enforcement."""

    policy_name: str = "disabled"

    async def acquire(
        self,
        *,
        bucket: str,
        tokens: int,
        route: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:  # pragma: no cover - no behavior yet
        return None

    def response_headers(self) -> dict[str, str]:
        return {"X-RateLimit-Policy": self.policy_name}

    def sse_metadata(self) -> dict[str, Any]:
        return {"rate_limit_policy": self.policy_name}


@dataclass(slots=True)
class BypassRateLimiter(NullRateLimiter):
    """Limiter used only when an explicit bypass flag is provided."""

    policy_name: str = "bypass"
    metadata: dict[str, Any] = field(
        default_factory=lambda: {"rate_limit_disabled": True, "configured": False}
    )

    def response_headers(self) -> dict[str, str]:
        return {"X-RateLimit-Policy": self.policy_name, "Viz-RateLimit-Bypass": "true"}

    def sse_metadata(self) -> dict[str, Any]:
        return dict(self.metadata)


__all__ = [
    "BypassRateLimiter",
    "NullRateLimiter",
    "RateLimiterProtocol",
]
