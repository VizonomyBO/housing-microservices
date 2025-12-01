"""Telemetry hooks for graph retrieval cache behavior.

Task 13 will wire real metrics; for Task 04 we expose a minimal protocol so the
node can record cache hits/misses without depending on a metrics backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class GraphRetrievalTelemetry(Protocol):
    """Interface for emitting cache events."""

    def record_hit(self, *, scope_hash: str | None, ttl_seconds: int | None) -> None: ...

    def record_miss(self, *, scope_hash: str | None, reason: str) -> None: ...


@dataclass(slots=True)
class NoOpGraphRetrievalTelemetry:
    """Fallback telemetry emitter that silently drops events."""

    def record_hit(
        self, *, scope_hash: str | None, ttl_seconds: int | None
    ) -> None:  # pragma: no cover - trivial
        return None

    def record_miss(
        self, *, scope_hash: str | None, reason: str
    ) -> None:  # pragma: no cover - trivial
        return None
