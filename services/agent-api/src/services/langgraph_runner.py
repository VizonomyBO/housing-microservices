"""LangGraph chat runner wiring HTTP requests to the agent graph."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.http.streaming import ChatRunResult
from agent_api.reduced_scope import ReducedScopeFlags
from cache import ValkeyCacheClientProtocol
from cache.response_serializer import CacheCitation
from guardrails.engine import GuardrailEngine
from models.retrieval import ChatRequestContext
from nodes.retrieval import AttachmentScopeLoaderNode, InputNormalizerNode
from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.graph.repository import GraphDataRepository
from nodes.retrieval.graph_retriever_node import GraphRetrieverNode
from nodes.retrieval.graph_summarizer_node import GraphSummarizerNode
from nodes.retrieval.utils.language import LanguageDetectorProtocol
from nodes.router.router_node import RouterNode
from repositories.conversation_scope_repository import ConversationScopeRepository
from services.answer_composer import OpenAIAnswerComposer
from services.model_clients import OpenAIChatClientProtocol
from state.agent_state import AgentState, MessageSnapshot
from streaming.sse_emitter import SSEEmitter
from subgraphs.informational.answer_synthesizer_node import AnswerSynthesizerNode
from telemetry import CacheObservability, MetricsRegistry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunnerContext:
    chat_request: ChatRequestContext
    request_context: RequestContext
    auth_context: AuthContext
    sse_emitter: SSEEmitter | None
    db_session: AsyncSession
    reduced_scope: ReducedScopeFlags | None


class LangGraphChatRunner:
    """Executes LangGraph nodes sequentially and streams SSE events."""

    def __init__(
        self,
        *,
        cache_client: ValkeyCacheClientProtocol,
        cache_observability: CacheObservability,
        language_detector: LanguageDetectorProtocol,
        openai_client: OpenAIChatClientProtocol | None,
        metrics: MetricsRegistry,
    ) -> None:
        self._cache_client = cache_client
        self._cache_observability = cache_observability
        self._language_detector = language_detector
        self._answer_composer = OpenAIAnswerComposer(client=openai_client)
        self._router = RouterNode(guardrail_engine=GuardrailEngine())
        self._metrics = metrics

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
        rate_limiter,
    ) -> ChatRunResult:
        if db_session is None:
            raise GatewayError(
                code="DATABASE_UNAVAILABLE",
                message="Database session is required",
                status_code=503,
            )
        state = self._build_initial_state(request)
        context = RunnerContext(
            chat_request=request,
            request_context=request_context,
            auth_context=auth,
            sse_emitter=sse_emitter,
            db_session=db_session,
            reduced_scope=reduced_scope,
        )
        try:
            final_state = await self._execute_pipeline(state, context)
        except GatewayError:
            raise
        except NodeError as exc:
            raise GatewayError(code=exc.code, message=exc.message, status_code=400) from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("LangGraph execution failed")
            raise GatewayError(
                code="INTERNAL_ERROR",
                message="LangGraph execution failed",
                status_code=500,
            ) from exc

        payload = self._build_done_payload(request, final_state)
        messages = self._build_messages(final_state)
        return ChatRunResult(done_payload=payload, messages=messages)

    async def _execute_pipeline(self, state: AgentState, context: RunnerContext) -> AgentState:
        state = await self._run_input_normalizer(state, context)
        state = await self._run_attachment_scope_loader(state, context)
        state = await self._run_graph_retriever(state, context)
        state = await self._run_graph_summarizer(state, context)
        state = await self._run_router(state, context)
        state = await self._run_answer(state, context)
        return state

    async def _run_input_normalizer(self, state: AgentState, context: RunnerContext) -> AgentState:
        repo = ConversationScopeRepository(context.db_session)
        node = InputNormalizerNode(
            request=context.chat_request,
            scope_repository=repo,
            language_detector=self._language_detector,
        )
        updates = await node(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    async def _run_attachment_scope_loader(
        self, state: AgentState, context: RunnerContext
    ) -> AgentState:
        scope_repo = ConversationScopeRepository(context.db_session)
        node = AttachmentScopeLoaderNode(scope_repository=scope_repo, workflow_repository=None)
        updates = await node(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    async def _run_graph_retriever(self, state: AgentState, context: RunnerContext) -> AgentState:
        repo = GraphDataRepository(context.db_session)
        node = GraphRetrieverNode(graph_repository=repo)
        updates = await node(state, sse_emitter=context.sse_emitter)
        if not updates:
            return state
        return state.model_copy(update=updates)

    async def _run_graph_summarizer(self, state: AgentState, context: RunnerContext) -> AgentState:
        node = GraphSummarizerNode()
        updates = await node(state, sse_emitter=context.sse_emitter)
        if not updates:
            return state
        return state.model_copy(update=updates)

    async def _run_router(self, state: AgentState, context: RunnerContext) -> AgentState:
        updates = await self._router(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    async def _run_answer(self, state: AgentState, context: RunnerContext) -> AgentState:
        answer_node = AnswerSynthesizerNode(
            composer=self._answer_composer,
            cache_client=self._cache_client,
            cache_observability=self._cache_observability,
        )
        updates = await answer_node(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    def _build_initial_state(self, request: ChatRequestContext) -> AgentState:
        snapshot = MessageSnapshot(
            message=HumanMessage(content=request.message.content),
            stored_at=datetime.now(UTC),
            metadata={"role": "user"},
        )
        flags = request.reduced_scope or ReducedScopeFlags()
        return AgentState(
            messages=[snapshot],
            conversation_id=request.conversation_id,
            reduced_scope_flags=flags,
        )

    def _build_done_payload(self, request: ChatRequestContext, state: AgentState) -> dict[str, Any]:
        answer = state.answer or ""
        citations = [c.model_dump() if isinstance(c, CacheCitation) else c for c in state.citations]
        route = state.route.value if state.route else None
        return {
            "status": "COMPLETED",
            "answer": answer,
            "thread_id": request.thread_id,
            "route": route,
            "citations": citations,
        }

    def _build_messages(self, state: AgentState) -> list[dict[str, str]]:
        answer = state.answer or ""
        return [{"role": "assistant", "content": answer}]


__all__ = ["LangGraphChatRunner", "RunnerContext"]
