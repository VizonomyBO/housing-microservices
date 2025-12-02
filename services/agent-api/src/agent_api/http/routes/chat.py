"""FastAPI router exposing POST /v1/chat."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.deps import (
    get_auth_context,
    get_chat_runner,
    get_request_context,
    get_stream_settings,
)
from agent_api.http.schemas import ChatRequestBody, ResponseMode
from agent_api.http.streaming import (
    ChatRunnerProtocol,
    StreamSettings,
    build_streaming_response,
    run_blocking_chat,
)
from models.retrieval import ChatRequestContext

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", summary="Invoke the LangGraph chat agent")
async def post_chat(
    payload: ChatRequestBody,
    chat_runner: Annotated[ChatRunnerProtocol, Depends(get_chat_runner)],
    request_context: Annotated[RequestContext, Depends(get_request_context)],
    auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    stream_settings: Annotated[StreamSettings, Depends(get_stream_settings)],
):
    thread_id = payload.thread_id or _generate_thread_id()
    chat_request = _build_request_context(payload, thread_id, auth_context)
    hints = dict(payload.hints or {})
    prompt_overrides = dict(payload.prompt_overrides or {})
    mode = payload.resolved_response_mode()

    if mode is ResponseMode.STREAM:
        return await build_streaming_response(
            runner=chat_runner,
            chat_request=chat_request,
            auth=auth_context,
            request_context=request_context,
            hints=hints,
            prompt_overrides=prompt_overrides,
            stream_settings=stream_settings,
        )

    return await run_blocking_chat(
        runner=chat_runner,
        chat_request=chat_request,
        auth=auth_context,
        request_context=request_context,
        hints=hints,
        prompt_overrides=prompt_overrides,
        stream_settings=stream_settings,
    )


def _build_request_context(
    payload: ChatRequestBody,
    thread_id: str,
    auth_context: AuthContext,
) -> ChatRequestContext:
    return payload.to_request_context(
        conversation_id=thread_id,
        owner_user_id=auth_context.user_id,
    )


def _generate_thread_id() -> str:
    return f"thr_{uuid4().hex}"


__all__ = ["router"]
