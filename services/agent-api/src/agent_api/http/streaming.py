"""Streaming orchestration helpers for the chat gateway."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.rate_limit import RateLimiterProtocol
from agent_api.http.schemas import BlockingChatResponse, ResponseMode
from agent_api.reduced_scope import ReducedScopeFlags, ReducedScopeSettings
from models.retrieval import ChatRequestContext
from streaming.events import SSEEventType, TaskErrorPayload
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import emit_demo_mode_event
from telemetry import CacheObservability, MetricsRegistry


@dataclass(slots=True)
class ChatRunResult:
    """Return value produced by the LangGraph runner."""

    done_payload: dict[str, Any]
    messages: list[dict[str, Any]] | None = None


class ChatRunnerProtocol(Protocol):
    """Interface implemented by the LangGraph chat runner."""

    async def run_chat(
        self,
        *,
        request: ChatRequestContext,
        auth: AuthContext,
        request_context: RequestContext,
        sse_emitter: SSEEmitter | None,
        prompt_overrides: dict[str, Any],
        hints: dict[str, Any],
        response_mode: ResponseMode,
        metrics: MetricsRegistry,
        cache_observability: CacheObservability,
        db_session: AsyncSession | None,
        reduced_scope: ReducedScopeFlags | None,
        rate_limiter: RateLimiterProtocol,
    ) -> ChatRunResult: ...


@dataclass(slots=True)
class StreamSettings:
    """Configuration knobs for the shared SSE emitter."""

    heartbeat_interval: float = 10.0
    max_queue_size: int = 256


@dataclass(slots=True)
class _StreamOutcome:
    status_code: int = 200
    result: ChatRunResult | None = None
    error: BaseException | None = None

    def as_error(self) -> GatewayError:
        if isinstance(self.error, GatewayError):
            return self.error
        message = str(self.error) if self.error else "Unknown error"
        return GatewayError(code="INTERNAL_ERROR", message=message, status_code=self.status_code)


class UnconfiguredChatRunner(ChatRunnerProtocol):
    """Fallback runner that raises when LangGraph wiring is missing."""

    async def run_chat(  # pragma: no cover - defensive guard
        self,
        *,
        request: ChatRequestContext,
        auth: AuthContext,
        request_context: RequestContext,
        sse_emitter: SSEEmitter | None,
        prompt_overrides: dict[str, Any],
        hints: dict[str, Any],
        response_mode: ResponseMode,
        metrics: MetricsRegistry,
        cache_observability: CacheObservability,
        db_session: AsyncSession | None,
        reduced_scope: ReducedScopeFlags | None,
        rate_limiter: RateLimiterProtocol,
    ) -> ChatRunResult:
        raise GatewayError(
            code="NOT_IMPLEMENTED",
            message="Chat runner not configured",
            status_code=501,
        )


async def build_streaming_response(
    *,
    runner: ChatRunnerProtocol,
    chat_request: ChatRequestContext,
    auth: AuthContext,
    request_context: RequestContext,
    hints: dict[str, Any],
    prompt_overrides: dict[str, Any],
    stream_settings: StreamSettings,
    metrics: MetricsRegistry,
    cache_observability: CacheObservability,
    db_session: AsyncSession | None,
    rate_limiter: RateLimiterProtocol,
    reduced_scope: ReducedScopeSettings | None = None,
    demo_metadata: dict[str, Any] | None = None,
) -> StreamingResponse:
    """Kick off the LangGraph run and expose its SSE iterator as a StreamingResponse."""

    emitter = _build_emitter(chat_request.conversation_id, request_context, stream_settings)
    await _emit_meta(
        emitter,
        chat_request,
        request_context,
        hints,
        demo_metadata=demo_metadata,
        limiter_metadata=rate_limiter.sse_metadata(),
    )

    outcome = _StreamOutcome()
    runner_task = asyncio.create_task(
        _invoke_runner(
            runner=runner,
            chat_request=chat_request,
            auth=auth,
            request_context=request_context,
            prompt_overrides=prompt_overrides,
            hints=hints,
            response_mode=ResponseMode.STREAM,
            emitter=emitter,
            outcome=outcome,
            metrics=metrics,
            cache_observability=cache_observability,
            db_session=db_session,
            reduced_scope=chat_request.reduced_scope,
            rate_limiter=rate_limiter,
        )
    )

    iterator = emitter.iter_sse()
    first_chunk_task = asyncio.create_task(_safe_anext(iterator))
    await asyncio.wait({first_chunk_task, runner_task}, return_when=asyncio.FIRST_COMPLETED)
    first_chunk = await first_chunk_task
    stream = _stream_generator(iterator, runner_task, first_chunk)
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    headers.update(rate_limiter.response_headers())
    if reduced_scope and reduced_scope.text_only_mode():
        headers.setdefault("X-Cache-Mode", "text-only")
        headers.setdefault("Viz-Demo-Mode", "text-only")
    else:
        headers.setdefault("X-Cache-Mode", "standard")
        headers.setdefault("Viz-Demo-Mode", "standard")
    response = StreamingResponse(stream, media_type="text/event-stream", headers=headers)
    response.status_code = outcome.status_code
    return response


async def run_blocking_chat(
    *,
    runner: ChatRunnerProtocol,
    chat_request: ChatRequestContext,
    auth: AuthContext,
    request_context: RequestContext,
    hints: dict[str, Any],
    prompt_overrides: dict[str, Any],
    stream_settings: StreamSettings,
    metrics: MetricsRegistry,
    cache_observability: CacheObservability,
    db_session: AsyncSession | None,
    rate_limiter: RateLimiterProtocol,
    reduced_scope: ReducedScopeSettings | None = None,
    demo_metadata: dict[str, Any] | None = None,
) -> JSONResponse:
    """Execute the LangGraph runner and return the canonical blocking response."""

    emitter = _build_emitter(chat_request.conversation_id, request_context, stream_settings)
    await _emit_meta(
        emitter,
        chat_request,
        request_context,
        hints,
        demo_metadata=demo_metadata,
        limiter_metadata=rate_limiter.sse_metadata(),
    )

    outcome = _StreamOutcome()
    runner_task = asyncio.create_task(
        _invoke_runner(
            runner=runner,
            chat_request=chat_request,
            auth=auth,
            request_context=request_context,
            prompt_overrides=prompt_overrides,
            hints=hints,
            response_mode=ResponseMode.BLOCKING,
            emitter=emitter,
            outcome=outcome,
            metrics=metrics,
            cache_observability=cache_observability,
            db_session=db_session,
            reduced_scope=chat_request.reduced_scope,
            rate_limiter=rate_limiter,
        )
    )
    drain_task = asyncio.create_task(_drain_emitter(emitter))
    try:
        await runner_task
    finally:
        await drain_task

    if outcome.error is not None or outcome.result is None:
        raise outcome.as_error()

    payload = BlockingChatResponse(
        thread_id=chat_request.thread_id,
        request_id=request_context.request_id,
        done=outcome.result.done_payload,
        messages=outcome.result.messages or [],
    )
    response = JSONResponse(status_code=200, content=payload.model_dump())
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers.update(rate_limiter.response_headers())
    if reduced_scope and reduced_scope.text_only_mode():
        response.headers.setdefault("X-Cache-Mode", "text-only")
        response.headers.setdefault("Viz-Demo-Mode", "text-only")
    else:
        response.headers.setdefault("X-Cache-Mode", "standard")
        response.headers.setdefault("Viz-Demo-Mode", "standard")
    return response


async def _invoke_runner(
    *,
    runner: ChatRunnerProtocol,
    chat_request: ChatRequestContext,
    auth: AuthContext,
    request_context: RequestContext,
    prompt_overrides: dict[str, Any],
    hints: dict[str, Any],
    response_mode: ResponseMode,
    emitter: SSEEmitter,
    outcome: _StreamOutcome,
    metrics: MetricsRegistry,
    cache_observability: CacheObservability,
    db_session: AsyncSession | None,
    reduced_scope: ReducedScopeFlags | None,
    rate_limiter: RateLimiterProtocol,
) -> None:
    try:
        result = await runner.run_chat(
            request=chat_request,
            auth=auth,
            request_context=request_context,
            sse_emitter=emitter,
            prompt_overrides=dict(prompt_overrides),
            hints=dict(hints),
            response_mode=response_mode,
            metrics=metrics,
            cache_observability=cache_observability,
            db_session=db_session,
            reduced_scope=reduced_scope,
            rate_limiter=rate_limiter,
        )
        if result is None:
            raise GatewayError(
                code="INTERNAL_ERROR",
                message="Chat runner returned an empty result",
                status_code=500,
            )
        outcome.result = result
        await emitter.emit(event=SSEEventType.DONE, payload=result.done_payload)
    except GatewayError as exc:
        outcome.error = exc
        outcome.status_code = exc.status_code
        await _emit_task_error(emitter, exc.code, exc.message, retryable=exc.status_code >= 500)
    except Exception as exc:  # pragma: no cover - defensive guard
        outcome.error = exc
        outcome.status_code = 500
        await _emit_task_error(
            emitter,
            code="INTERNAL_ERROR",
            message="Unexpected error during chat execution",
            retryable=True,
            details={"exception": exc.__class__.__name__},
        )
    finally:
        await emitter.close()


def _build_emitter(
    conversation_id: str,
    request_context: RequestContext,
    stream_settings: StreamSettings,
) -> SSEEmitter:
    return SSEEmitter(
        conversation_id=conversation_id,
        task_id=f"run_{uuid4().hex}",
        request_id=request_context.request_id,
        heartbeat_interval=stream_settings.heartbeat_interval,
        max_queue_size=stream_settings.max_queue_size,
    )


async def _emit_meta(
    emitter: SSEEmitter,
    chat_request: ChatRequestContext,
    request_context: RequestContext,
    hints: dict[str, Any],
    *,
    demo_metadata: dict[str, Any] | None = None,
    limiter_metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "thread_id": chat_request.thread_id,
        "session_id": chat_request.session_id,
        "request_id": request_context.request_id,
        "route_hint": hints.get("route"),
    }
    if demo_metadata:
        payload["reduced_scope"] = demo_metadata
    if limiter_metadata:
        payload["rate_limit"] = limiter_metadata
    await emitter.emit(event=SSEEventType.META, payload=payload)
    if demo_metadata and demo_metadata.get("enabled"):
        await emit_demo_mode_event(
            emitter,
            capability="demo_mode",
            metadata=demo_metadata,
        )


async def _emit_task_error(
    emitter: SSEEmitter,
    code: str,
    message: str,
    *,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> None:
    payload = TaskErrorPayload(
        code=code, message=message, retryable=retryable, details=details or {}
    )
    await emitter.emit(event=SSEEventType.TASK_ERROR, payload=payload)


async def _safe_anext(iterator: AsyncIterator[str]) -> str | None:
    try:
        return await iterator.__anext__()
    except StopAsyncIteration:  # pragma: no cover - defensive
        return None


async def _drain_emitter(emitter: SSEEmitter) -> None:
    async for _ in emitter.iter_sse():
        continue


async def _stream_generator(
    iterator: AsyncIterator[str],
    runner_task: asyncio.Task[None],
    first_chunk: str | None,
) -> AsyncIterator[str]:
    try:
        if first_chunk is not None:
            yield first_chunk
        async for chunk in iterator:
            yield chunk
    finally:
        await runner_task


__all__ = [
    "ChatRunResult",
    "ChatRunnerProtocol",
    "StreamSettings",
    "UnconfiguredChatRunner",
    "build_streaming_response",
    "run_blocking_chat",
]
