"""Streaming helpers wrapping the chat runner."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.runner import ChatRunnerProtocol, ChatRunResult
from agent_api.auth.validator import AuthContext
from agent_api.http.context import RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import BlockingChatResponse, ResponseMode
from agent_api.models.chat import ChatRequestContext
from streaming.events import SSEEventType, TaskErrorPayload
from streaming.sse_emitter import SSEEmitter, StreamSettings

logger = logging.getLogger(__name__)


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


async def build_streaming_response(
    *,
    runner: ChatRunnerProtocol,
    chat_request: ChatRequestContext,
    auth: AuthContext,
    request_context: RequestContext,
    hints: dict[str, Any],
    prompt_overrides: dict[str, Any],
    stream_settings: StreamSettings,
    db_session: AsyncSession | None,
) -> StreamingResponse:
    emitter = _build_emitter(chat_request.conversation_id, request_context, stream_settings)
    await _emit_meta(emitter, chat_request, request_context, hints)

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
            db_session=db_session,
        )
    )

    iterator = emitter.iter_sse()
    stream = _stream_generator(iterator, runner_task)
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
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
    db_session: AsyncSession | None,
) -> JSONResponse:
    emitter = _build_emitter(chat_request.conversation_id, request_context, stream_settings)
    await _emit_meta(emitter, chat_request, request_context, hints)

    outcome = _StreamOutcome()
    await _invoke_runner(
        runner=runner,
        chat_request=chat_request,
        auth=auth,
        request_context=request_context,
        prompt_overrides=prompt_overrides,
        hints=hints,
        response_mode=ResponseMode.BLOCKING,
        emitter=emitter,
        outcome=outcome,
        db_session=db_session,
    )

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
    db_session: AsyncSession | None,
) -> None:
    try:
        result = await runner.run_chat(
            request=chat_request,
            auth=auth,
            request_context=request_context,
            sse_emitter=emitter,
            prompt_overrides=prompt_overrides,
            hints=hints,
            response_mode=response_mode,
            db_session=db_session,
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
    except Exception as exc:  # pragma: no cover
        outcome.error = exc
        outcome.status_code = 500
        logger.exception("Unexpected error during chat execution", exc_info=exc)
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
) -> None:
    payload = {
        "thread_id": chat_request.thread_id,
        "session_id": chat_request.session_id,
        "request_id": request_context.request_id,
        "route_hint": hints.get("route"),
    }
    await emitter.emit(event=SSEEventType.META, payload=payload)


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


async def _stream_generator(iterator, runner_task: asyncio.Task[None]) -> Any:
    try:
        async for chunk in iterator:
            yield chunk
    finally:
        await runner_task


__all__ = ["build_streaming_response", "run_blocking_chat"]
