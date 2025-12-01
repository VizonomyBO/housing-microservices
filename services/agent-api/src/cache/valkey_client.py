"""Valkey client stubs used by the retrieval service.

Real Valkey wiring ships in Task 07/13; this module exposes interfaces +
in-memory implementations so LangGraph nodes can be exercised in unit tests
without opening network connections.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

Clock = Callable[[], datetime]


class ValkeyCacheClientProtocol(Protocol):
    """Protocol describing the Valkey cache client surface area."""

    async def get(self, key: str) -> bytes | None: ...

    async def set(
        self, key: str, value: bytes | str, *, ttl_seconds: int | None = None
    ) -> None: ...

    async def tag_hit(self, key: str) -> None: ...

    async def tag_miss(self, key: str, *, reason: str | None = None) -> None: ...


@dataclass(slots=True)
class InMemoryValkeyClient(ValkeyCacheClientProtocol):
    """In-memory Valkey stand-in useful for unit tests and local dev."""

    default_ttl_seconds: int = 60 * 60 * 48
    clock: Clock = field(default=lambda: datetime.now(UTC))
    _store: dict[str, tuple[bytes, float | None]] = field(default_factory=dict)
    telemetry: list[dict[str, str]] = field(default_factory=list)

    async def get(self, key: str) -> bytes | None:
        record = self._store.get(key)
        if record is None:
            return None
        value, expires_at = record
        if expires_at is not None and expires_at <= self._now_ts():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: bytes | str, *, ttl_seconds: int | None = None) -> None:
        payload = value.encode("utf-8") if isinstance(value, str) else value
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = self._now_ts() + ttl if ttl else None
        self._store[key] = (payload, expires_at)

    async def tag_hit(self, key: str) -> None:
        self.telemetry.append({"event": "hit", "key": key})

    async def tag_miss(self, key: str, *, reason: str | None = None) -> None:
        payload = {"event": "miss", "key": key}
        if reason:
            payload["reason"] = reason
        self.telemetry.append(payload)

    def _now_ts(self) -> float:
        return self.clock().timestamp()


__all__ = ["InMemoryValkeyClient", "ValkeyCacheClientProtocol"]
