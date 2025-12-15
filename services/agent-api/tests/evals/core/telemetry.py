from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievalEvent:
    """A single retrieval trace entry."""

    chunk_id: str
    score: float | None = None
    latency_ms: float | None = None
    content_preview: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class EvalTelemetrySink:
    """Captures retrieval traces emitted during eval runs."""

    def __init__(self) -> None:
        self._events: list[RetrievalEvent] = []

    def record(
        self,
        *,
        chunk_id: str,
        score: float | None = None,
        latency_ms: float | None = None,
        content_preview: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(
            RetrievalEvent(
                chunk_id=chunk_id,
                score=score,
                latency_ms=latency_ms,
                content_preview=content_preview,
                metadata=metadata or {},
            )
        )

    @property
    def events(self) -> list[RetrievalEvent]:
        return list(self._events)

    def as_dict(self) -> list[dict[str, Any]]:
        return [asdict(event) for event in self._events]

    def summary(self) -> dict[str, Any]:
        return {
            "count": len(self._events),
            "avg_latency_ms": (
                sum(event.latency_ms or 0.0 for event in self._events) / len(self._events)
                if self._events
                else 0.0
            ),
            "chunk_ids": [event.chunk_id for event in self._events],
        }
