"""Helpers for instrumenting LangGraph nodes with SSE lifecycle events."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, MutableMapping
from collections.abc import MutableMapping as MutableMappingABC
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

from streaming.events import (
    CacheEventPayload,
    SSEEventType,
    TaskLifecyclePayload,
    TelemetrySnapshotPayload,
)
from streaming.sse_emitter import SSEEmitter

if TYPE_CHECKING:  # pragma: no cover - import-time guard
    from guardrails import RouterRoute
else:  # pragma: no cover - runtime fallback when guardrails not loaded
    RouterRoute = Any  # type: ignore[misc, assignment]

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class LifecycleContext:
    """Holds mutable metadata for the current node/span."""

    node: str
    subgraph: str | None = None
    route: str | None = None
    sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_route(self, route: str | RouterRoute | None) -> None:  # type: ignore[name-defined]
        if route is None:
            return
        if hasattr(route, "value"):
            self.route = str(route.value)
        else:
            self.route = str(route)

    def add_metadata(self, **entries: Any) -> None:
        self.metadata.update(entries)

    def snapshot(self, *, status: str | None = None) -> dict[str, Any]:
        data = dict(self.metadata)
        if status is not None:
            data["status"] = status
        return data

    def to_payload(self, *, metadata: Mapping[str, Any]) -> TaskLifecyclePayload:
        return TaskLifecyclePayload(
            node=self.node,
            subgraph=self.subgraph,
            route=self.route,
            sequence=self.sequence,
            metadata=metadata,
        )


_CURRENT_SPAN: ContextVar[LifecycleContext | None] = ContextVar(
    "sse_lifecycle_context", default=None
)


def current_span() -> LifecycleContext | None:
    """Return the active lifecycle context if one exists."""

    return _CURRENT_SPAN.get()


def add_metadata(**entries: Any) -> None:
    """Update metadata for the active span (no-op when unset)."""

    span = current_span()
    if span is None:
        return
    span.add_metadata(**entries)


def set_route(route: str | RouterRoute | None) -> None:  # type: ignore[name-defined]
    """Attach a router route string to the active span."""

    span = current_span()
    if span is None:
        return
    span.set_route(route)


@asynccontextmanager
async def lifecycle_span(
    *,
    emitter: SSEEmitter | None,
    node: str,
    subgraph: str | None = None,
    route: str | None = None,
    sequence: int | None = None,
    metadata: MutableMapping[str, Any] | None = None,
) -> AsyncIterator[LifecycleContext]:
    """Context manager sending task_start/task_end events around a node."""

    span = LifecycleContext(
        node=node,
        subgraph=subgraph,
        route=route,
        sequence=sequence,
        metadata=dict(metadata or {}),
    )
    token = _CURRENT_SPAN.set(span)
    try:
        if emitter is not None:
            start_payload = span.to_payload(metadata=span.snapshot(status="running"))
            await emitter.emit(event=SSEEventType.TASK_START, payload=start_payload)
        yield span
    except Exception as exc:
        if emitter is not None:
            span.add_metadata(error=str(exc))
            end_payload = span.to_payload(metadata=span.snapshot(status="error"))
            await emitter.emit(event=SSEEventType.TASK_END, payload=end_payload)
        raise
    else:
        if emitter is not None:
            end_payload = span.to_payload(metadata=span.snapshot(status="success"))
            await emitter.emit(event=SSEEventType.TASK_END, payload=end_payload)
    finally:
        _CURRENT_SPAN.reset(token)


def instrumented(
    node: str,
    *,
    subgraph: str | None = None,
) -> Callable[[F], F]:
    """Decorator that wraps async LangGraph nodes with lifecycle_span."""

    def decorator(func: F) -> F:
        async def _wrapper(*args: Any, **kwargs: Any) -> Any:
            emitter = kwargs.get("sse_emitter")
            metadata = kwargs.pop("sse_metadata", None)
            async with lifecycle_span(
                emitter=emitter,
                node=node,
                subgraph=subgraph,
                metadata=metadata if isinstance(metadata, MutableMappingABC) else None,
            ):
                return await func(*args, **kwargs)

        return wraps(func)(_wrapper)  # type: ignore[return-value]

    return decorator


__all__ = [
    "LifecycleContext",
    "add_metadata",
    "current_span",
    "emit_cache_hit",
    "emit_cache_miss",
    "emit_cache_write",
    "emit_telemetry_snapshot",
    "instrumented",
    "lifecycle_span",
    "set_route",
]


async def emit_cache_hit(
    emitter: SSEEmitter | None,
    *,
    cache_key: str,
    namespace: str | None = None,
    latency_ms: float | None = None,
    payload_hash: str | None = None,
) -> None:
    await _emit_cache_event(
        emitter,
        event=SSEEventType.CACHE_HIT,
        cache_key=cache_key,
        namespace=namespace,
        hit=True,
        latency_ms=latency_ms,
        payload_hash=payload_hash,
    )


async def emit_cache_miss(
    emitter: SSEEmitter | None,
    *,
    cache_key: str,
    namespace: str | None = None,
    latency_ms: float | None = None,
    reason: str | None = None,
) -> None:
    metadata = {} if reason is None else {"reason": reason}
    await _emit_cache_event(
        emitter,
        event=SSEEventType.CACHE_MISS,
        cache_key=cache_key,
        namespace=namespace,
        hit=False,
        latency_ms=latency_ms,
        extra_metadata=metadata,
    )


async def emit_cache_write(
    emitter: SSEEmitter | None,
    *,
    cache_key: str,
    namespace: str | None = None,
    ttl_seconds: int | None = None,
    payload_hash: str | None = None,
) -> None:
    await _emit_cache_event(
        emitter,
        event=SSEEventType.CACHE_WRITE,
        cache_key=cache_key,
        namespace=namespace,
        hit=False,
        ttl_seconds=ttl_seconds,
        payload_hash=payload_hash,
    )


async def emit_telemetry_snapshot(
    emitter: SSEEmitter | None,
    *,
    metrics: Mapping[str, Any],
    labels: Mapping[str, str] | None = None,
    window_ms: int | None = None,
) -> None:
    if emitter is None:
        return
    payload = TelemetrySnapshotPayload(
        metrics=dict(metrics),
        labels=dict(labels or {}),
        window_ms=window_ms,
    )
    await emitter.emit(event=SSEEventType.TELEMETRY_SNAPSHOT, payload=payload)


async def _emit_cache_event(
    emitter: SSEEmitter | None,
    *,
    event: SSEEventType,
    cache_key: str,
    namespace: str | None,
    hit: bool | None,
    latency_ms: float | None = None,
    ttl_seconds: int | None = None,
    payload_hash: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> None:
    if emitter is None:
        return
    payload = CacheEventPayload(
        cache_key=cache_key,
        namespace=namespace or _infer_namespace(cache_key),
        hit=hit,
        source="valkey",
        latency_ms=latency_ms,
        ttl_seconds=ttl_seconds,
        payload_hash=payload_hash,
        metadata=dict(extra_metadata or {}),
    )
    await emitter.emit(event=event, payload=payload)


def _infer_namespace(cache_key: str) -> str | None:
    if ":" not in cache_key:
        return None
    return cache_key.split(":", 1)[0]
