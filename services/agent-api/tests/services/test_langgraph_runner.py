from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.reduced_scope import ReducedScopeFlags
from cache import InMemoryValkeyClient
from cache.response_serializer import CacheCitation
from models.retrieval import (
    AttachmentDocument,
    AttachmentDocumentChunk,
    AttachmentScope,
    ChatConstraints,
    ChatMessagePayload,
    ChatRequestContext,
    NormalizedInput,
    TenantScope,
)
from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.utils.language import StubLanguageDetector
from nodes.router.router_node import RouterRoute
from services.langgraph_runner import LangGraphChatRunner, RunnerContext
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


def _kpi_document() -> AttachmentDocument:
    table_text = """
    ### KPI Table (Nov 2024)

    | City / Zone | KPI | Value |
    |-------------|-----|-------|
    | Arroyo Vista | Housing Stability Score | 78 |
    | Brookhaven | Housing Stability Score | 82 |
    | District 9 Core | Housing Stability Score | 88 |
    | District 9 East | Voucher Utilization % | 91 |
    """.strip()
    return AttachmentDocument(
        document_id="doc-kpi",
        canonical_name="District 9 KPI Dashboard",
        access_scope="base",
        chunks=[AttachmentDocumentChunk(chunk_id="chunk-1", text=table_text)],
    )


def _normalized_prompt(text: str) -> NormalizedInput:
    return NormalizedInput(
        normalized_prompt=text,
        raw_prompt=text,
        tenant_scope=TenantScope(conversation_id="conv-1", thread_id="thr-1"),
        attachment_refs=[],
        scope_hash="scope",
    )


def _runner(metrics):
    return LangGraphChatRunner(
        cache_client=InMemoryValkeyClient(),
        cache_observability=CacheObservability(metrics=metrics),
        language_detector=StubLanguageDetector(language_code="en", confidence=1.0),
        openai_client=None,
        metrics=metrics,
    )


def test_done_payload_includes_sql_row_count(db_session):
    metrics = get_metrics_registry()
    runner = _runner(metrics)
    request = _chat_request()
    base_state = runner._build_initial_state(request)
    state = base_state.model_copy(
        update={
            "requires_sql": True,
            "answer": "numeric",
            "route": RouterRoute.NUMERICAL,
            "citations": [],
            "numerical_trace": {
                "sql_queries": ["SELECT * FROM ledger"],
                "executor": {"row_count": 4},
                "table_results": [{"city": "Austin"}],
            },
            "numerical_result_rows": [{"city": "Austin"}],
        }
    )
    payload = runner._build_done_payload(request, state)
    assert payload["sql_row_count"] == 4
    assert payload["table_results"] == [{"city": "Austin"}]


def test_builds_numerical_table_from_markdown(db_session):
    metrics = get_metrics_registry()
    runner = _runner(metrics)
    state = runner._build_initial_state(_chat_request()).model_copy(
        update={
            "attachment_scope": AttachmentScope(documents=[_kpi_document()]),
        }
    )
    tables = runner._build_numerical_tables(state)
    assert tables
    assert tables[0].row_count == 4
    assert tables[0].columns[-1].name == "value"


@pytest.mark.asyncio
async def test_numerical_pipeline_executes_sql(db_session):
    metrics = get_metrics_registry()
    runner = _runner(metrics)
    request = _chat_request()
    base_state = runner._build_initial_state(request)
    state = base_state.model_copy(
        update={
            "normalized_input": _normalized_prompt(
                "While reviewing the KPI dashboard for our cities, point out anyone crossing the 80-point stability trigger and explain what action they need."
            ),
            "attachment_scope": AttachmentScope(documents=[_kpi_document()]),
            "requires_sql": True,
        }
    )
    context = RunnerContext(
        chat_request=request,
        request_context=RequestContext(
            request_id="req-1", traceparent=None, idempotency_key=None, headers={}
        ),
        auth_context=AuthContext(user_id="user-1"),
        sse_emitter=None,
        db_session=db_session,
        reduced_scope=ReducedScopeFlags(),
    )
    state = await runner._run_numerical_pipeline(state, context)
    assert state.numerical_result_rows
    assert state.numerical_trace["executor"]["row_count"] == 3
    assert "sql_queries" in state.numerical_trace
