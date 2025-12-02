"""Rate limiter protocols + reduced-scope shims for the HTTP gateway."""

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
    """Default limiter that performs no enforcement."""

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
class ReducedScopeRateLimiter(NullRateLimiter):
    """Limiter shim used when reduced scope disables Valkey/token buckets."""

    policy_name: str = "demo-mode"
    metadata: dict[str, Any] = field(default_factory=lambda: {"rate_limit_disabled": True})

    def response_headers(self) -> dict[str, str]:
        return {"X-RateLimit-Policy": self.policy_name, "Viz-Demo-Mode": "rate-limit"}

    def sse_metadata(self) -> dict[str, Any]:
        return dict(self.metadata)


@dataclass(slots=True)
class ValkeyRateLimiterStub(NullRateLimiter):
    """Placeholder for the production Valkey-backed limiter."""

    policy_name: str = "valkey"

    async def acquire(
        self,
        *,
        bucket: str,
        tokens: int,
        route: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        # TODO(epic-04): integrate Valkey-backed limiter once reduced scope lifts.
        return None


__all__ = [
    "NullRateLimiter",
    "RateLimiterProtocol",
    "ReducedScopeRateLimiter",
    "ValkeyRateLimiterStub",
]
