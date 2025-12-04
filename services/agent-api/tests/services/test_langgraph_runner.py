from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.reduced_scope import ReducedScopeFlags
from cache import InMemoryValkeyClient
from cache.response_serializer import CacheCitation
from models.retrieval import ChatConstraints, ChatMessagePayload, ChatRequestContext
from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.utils.language import StubLanguageDetector
from nodes.router.router_node import RouterRoute
from services.langgraph_runner import LangGraphChatRunner
from telemetry import CacheObservability, get_metrics_registry


def _chat_request() -> ChatRequestContext:
    message = ChatMessagePayload(content="hello world")
    return ChatRequestContext(
        conversation_id="conv-1",
        thread_id="thr-1",
        session_id="sess-1",
        message=message,
        hints={},
        owner_user_id="user-1",
        constraints=ChatConstraints(),
    )


@pytest.mark.asyncio
async def test_runner_returns_answer(db_session):
    metrics = get_metrics_registry()
    runner = LangGraphChatRunner(
        cache_client=InMemoryValkeyClient(),
        cache_observability=CacheObservability(metrics=metrics),
        language_detector=StubLanguageDetector(language_code="en", confidence=1.0),
        openai_client=None,
        metrics=metrics,
    )
    request = _chat_request()
    final_state = runner._build_initial_state(request).model_copy(
        update={
            "answer": "stub-answer",
            "route": RouterRoute.INFORMATIONAL,
            "citations": [CacheCitation(doc_id="doc-1", chunk_id="chunk-1")],
        }
    )
    with patch.object(runner, "_execute_pipeline", AsyncMock(return_value=final_state)):
        result = await runner.run_chat(
            request=request,
            auth=AuthContext(user_id="user-1"),
            request_context=RequestContext(
                request_id="req-1", traceparent=None, idempotency_key=None, headers={}
            ),
            sse_emitter=None,
            prompt_overrides={},
            hints={},
            response_mode=ResponseMode.STREAM,
            metrics=metrics,
            cache_observability=CacheObservability(metrics=metrics),
            db_session=db_session,
            reduced_scope=ReducedScopeFlags(),
            rate_limiter=None,
        )
    assert result.done_payload["answer"] == "stub-answer"
    assert result.messages is not None
    assert result.messages[0]["content"] == "stub-answer"


@pytest.mark.asyncio
async def test_runner_maps_node_errors(db_session):
    metrics = get_metrics_registry()
    runner = LangGraphChatRunner(
        cache_client=InMemoryValkeyClient(),
        cache_observability=CacheObservability(metrics=metrics),
        language_detector=StubLanguageDetector(language_code="en", confidence=1.0),
        openai_client=None,
        metrics=metrics,
    )
    with (
        patch.object(
            runner,
            "_execute_pipeline",
            AsyncMock(side_effect=NodeError(code="BAD", message="boom")),
        ),
        pytest.raises(GatewayError) as excinfo,
    ):
        await runner.run_chat(
            request=_chat_request(),
            auth=AuthContext(user_id="user-1"),
            request_context=RequestContext(
                request_id="req-1", traceparent=None, idempotency_key=None, headers={}
            ),
            sse_emitter=None,
            prompt_overrides={},
            hints={},
            response_mode=ResponseMode.STREAM,
            metrics=metrics,
            cache_observability=CacheObservability(metrics=metrics),
            db_session=db_session,
            reduced_scope=ReducedScopeFlags(),
            rate_limiter=None,
        )
    assert excinfo.value.status_code == 400
