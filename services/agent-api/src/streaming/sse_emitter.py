"""Async SSE emitter and iterator utilities."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from streaming.events import (
    EVENT_PAYLOAD_MODEL,
    PayloadType,
    SSEEnvelope,
    SSEEventType,
    SSEPayload,
    build_envelope,
)

logger = logging.getLogger(__name__)


class SSEEmitterError(RuntimeError):
    """Raised when the SSE emitter cannot produce a valid frame."""


HeartbeatFormatter = Callable[[], str]
EventEmitterFn = Callable[[str, Mapping[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class SSEEmitter:
    """Queues LangGraph events and exposes an async iterator for SSE streaming."""

    conversation_id: str
    task_id: str | None = None
    request_id: str | None = None
    heartbeat_interval: float = 15.0
    max_queue_size: int = 128
    heartbeat_formatter: HeartbeatFormatter | None = None
    _queue: asyncio.Queue[str | None] = field(init=False, repr=False)
    _sequence_id: int = field(init=False, repr=False, default=0)
    _closed: bool = field(init=False, repr=False, default=False)
    _dropped: int = field(init=False, repr=False, default=0)

    def __post_init__(self) -> None:
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be > 0")
        if self.max_queue_size <= 0:
            raise ValueError("max_queue_size must be > 0")
        self._queue = asyncio.Queue(maxsize=self.max_queue_size)

    @property
    def dropped_events(self) -> int:
        return self._dropped

    def as_event_emitter(self) -> EventEmitterFn:
        async def _emit(event: str, payload: Mapping[str, Any]) -> None:
            await self.emit(event=event, payload=payload)

        return _emit

    async def emit(
        self,
        *,
        event: str | SSEEventType,
        payload: PayloadType | Mapping[str, Any],
        conversation_id: str | None = None,
        task_id: str | None = None,
        request_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> SSEEnvelope:
        """Validate payloads and enqueue formatted SSE frames."""

        event_type = self._coerce_event(event)
        payload_model = self._coerce_payload(event_type, payload)
        envelope = build_envelope(
            event=event_type,
            conversation_id=conversation_id or self.conversation_id,
            task_id=task_id or self.task_id,
            payload=payload_model,
            request_id=request_id or self.request_id,
            timestamp=timestamp,
        )
        await self._enqueue(self._format(envelope))
        return envelope

    async def send_envelope(self, envelope: SSEEnvelope) -> None:
        """Queue a pre-built envelope."""

        await self._enqueue(self._format(envelope))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._enqueue(None)

    def __aiter__(self) -> AsyncIterator[str]:
        return self.iter_sse()

    async def iter_sse(self) -> AsyncIterator[str]:
        """Yield SSE frames with heartbeat keepalives."""

        while True:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=self.heartbeat_interval)
            except TimeoutError:
                if self._closed:
                    break
                yield self._heartbeat()
                continue
            except asyncio.CancelledError:
                await self.close()
                raise

            if item is None:
                break
            yield item

    async def _enqueue(self, item: str | None) -> None:
        while True:
            try:
                self._queue.put_nowait(item)
                break
            except asyncio.QueueFull:
                try:
                    discarded = self._queue.get_nowait()
                    if discarded is not None:
                        self._dropped += 1
                        if self._dropped == 1:
                            logger.warning(
                                "SSE emitter queue full for conversation_id=%s; dropping oldest frame",
                                self.conversation_id,
                            )
                except asyncio.QueueEmpty:  # pragma: no cover - defensive
                    await asyncio.sleep(0)

    def _heartbeat(self) -> str:
        if self.heartbeat_formatter:
            return self.heartbeat_formatter()
        return ": keep-alive\n\n"

    def _format(self, envelope: SSEEnvelope) -> str:
        self._sequence_id += 1
        payload = json.dumps(envelope.as_dict(), separators=(",", ":"), ensure_ascii=False)
        lines = [
            f"id: {self._sequence_id}",
            f"event: {envelope.event.value}",
            f"data: {payload}",
        ]
        return "\n".join(lines) + "\n\n"

    def _coerce_event(self, event: str | SSEEventType) -> SSEEventType:
        if isinstance(event, SSEEventType):
            return event
        try:
            return SSEEventType(event)
        except ValueError as exc:  # pragma: no cover - guardrail
            raise SSEEmitterError(f"Unsupported SSE event: {event}") from exc

    def _coerce_payload(
        self, event: SSEEventType, payload: PayloadType | Mapping[str, Any]
    ) -> PayloadType:
        if isinstance(payload, SSEPayload):
            return payload
        model = EVENT_PAYLOAD_MODEL.get(event, SSEPayload)
        return model.model_validate(payload)


def default_event_emitter(emitter: SSEEmitter) -> EventEmitterFn:
    """Convenience helper wired into services that expect a callable emitter."""

    return emitter.as_event_emitter()
