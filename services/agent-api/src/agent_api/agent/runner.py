"""Chat runner that wraps the LangGraph ReAct agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.agent.graph import DEFAULT_SYSTEM_PROMPT, build_agent_graph
from agent_api.agent.tool_runtime import ToolRuntime, set_runtime
from agent_api.agent.tools import (
    compute_over_chunks,
    document_status,
    list_attachments,
    pyodide_sandbox,
    retrieve_documents,
)
from agent_api.auth.validator import AuthContext
from agent_api.clients import OpenAIChatClient, VoyageEmbeddingClient, VoyageRerankClient
from agent_api.http.context import RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.models.chat import ChatRequestContext
from agent_api.services.conversations import ConversationService
from agent_api.services.retrieval import RetrievalService
from agent_api.services.retrieval_scope import ConversationScopeRepository
from agent_api.settings import Settings
from streaming.events import SSEEventType, TaskLifecyclePayload
from streaming.sse_emitter import SSEEmitter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatRunResult:
    done_payload: dict[str, Any]
    messages: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatRunnerProtocol(Protocol):
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
        db_session: AsyncSession | None,
    ) -> ChatRunResult: ...


class UnconfiguredRunner(ChatRunnerProtocol):
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
        db_session: AsyncSession | None,
    ) -> ChatRunResult:
        raise GatewayError(
            code="NOT_IMPLEMENTED", message="Chat runner not configured", status_code=501
        )


class LangGraphRunner(ChatRunnerProtocol):
    def __init__(self, *, settings: Settings):
        self._settings = settings
        llm_factory: Any = cast(Any, ChatOpenAI)
        self._llm: ChatOpenAI = llm_factory(
            api_key=settings.openai_api_key,
            model=settings.openai_chat_model,
            temperature=0.1,
        )
        self._chat_client = OpenAIChatClient(
            api_key=settings.openai_api_key or "", model=settings.openai_chat_model
        )
        self._embedding_client = VoyageEmbeddingClient(
            api_key=settings.voyage_api_key or "",
            model=settings.voyage_embedding.model,
        )
        self._rerank_client = VoyageRerankClient(
            api_key=settings.voyage_api_key or "",
            model=settings.voyage_rerank_model,
        )
        self._system_prompt = DEFAULT_SYSTEM_PROMPT
        self._agent = build_agent_graph(
            llm=self._llm,
            tools=[
                retrieve_documents,
                document_status,
                list_attachments,
                pyodide_sandbox,
                compute_over_chunks,
            ],
            system_prompt=self._system_prompt,
        )

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
        db_session: AsyncSession | None,
    ) -> ChatRunResult:
        if db_session is None:
            raise GatewayError(
                code="DATABASE_UNAVAILABLE",
                message="Database session is required",
                status_code=503,
            )
        if not request.message or not request.message.content:
            raise GatewayError(
                code="VALIDATION_ERROR",
                message="Message content is required",
                status_code=400,
            )

        if sse_emitter:
            await sse_emitter.emit(
                event=SSEEventType.TASK_START,
                payload=TaskLifecyclePayload(node="react_agent", metadata={}),
            )

        scope_repo = ConversationScopeRepository(db_session)
        attachments = await scope_repo.list_conversation_documents(request.conversation_id)
        if not attachments:
            raise GatewayError(
                code="ATTACHMENTS_REQUIRED",
                message="No documents attached to this conversation. Please attach documents first.",
                status_code=400,
            )
        summaries = await scope_repo.hydrate_documents([att.document_id for att in attachments])
        active_ids = [doc_id for doc_id, summary in summaries.items() if summary.status == "active"]
        if not active_ids:
            raise GatewayError(
                code="DOCUMENTS_INACTIVE",
                message="Attached documents are not active yet; wait for ingestion to complete.",
                status_code=409,
            )

        retrieval_service = RetrievalService(
            scope_repo=scope_repo,
            embedding_client=self._embedding_client,
            rerank_client=self._rerank_client,
            chat_client=self._chat_client,
        )
        runtime = ToolRuntime(
            conversation_id=request.conversation_id,
            owner_user_id=request.owner_user_id,
            auth=auth,
            db_session=db_session,
            retrieval=retrieval_service,
            request_id=request_context.request_id,
            pyodide=self._settings.pyodide,
            metadata={"hints": hints},
        )
        set_runtime(runtime)

        convo_service = ConversationService(db_session)
        await convo_service.append_message(
            conversation_id=request.conversation_id,
            role="user",
            content=request.message.model_dump(mode="json"),
        )

        human = HumanMessage(content=request.message.content)
        system = SystemMessage(content=self._system_prompt)
        config = {"configurable": {"thread_id": request.thread_id}}
        result = await self._agent.ainvoke({"messages": [system, human]}, config=config)

        ai_content = ""
        if isinstance(result, dict):
            messages = result.get("messages") or []
            if messages:
                last = messages[-1]
                if isinstance(last, AIMessage):
                    ai_content = last.content or ""
                elif isinstance(last, dict):
                    ai_content = last.get("content") or ""
        if not ai_content:
            ai_content = "I'm sorry, I couldn't produce a response."

        tool_calls = _extract_tool_history(
            result.get("messages") if isinstance(result, dict) else None
        )
        citations = runtime.last_retrieval.citations if runtime.last_retrieval else []
        if not citations:
            raise GatewayError(
                code="MISSING_CITATIONS",
                message="Unable to produce cited answer; retrieval did not yield citations.",
                status_code=502,
            )

        await convo_service.append_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content={"content": ai_content, "citations": citations},
        )

        if sse_emitter:
            await sse_emitter.emit(
                event=SSEEventType.TASK_END,
                payload=TaskLifecyclePayload(node="react_agent", metadata={}),
            )

        payload = {
            "status": "COMPLETED",
            "answer": ai_content,
            "thread_id": request.thread_id,
            "route": "react",
            "citations": citations,
            "requires_sql": False,
            "tool_calls": tool_calls,
        }
        messages = [{"role": "assistant", "content": ai_content}]
        return ChatRunResult(done_payload=payload, messages=messages, tool_calls=tool_calls)


def _extract_tool_history(messages: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    if not messages:
        return history
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls or []:
                history.append(
                    {
                        "type": "tool_call",
                        "name": call.get("name"),
                        "id": call.get("id"),
                        "args": call.get("args"),
                    }
                )
        elif isinstance(msg, ToolMessage):
            history.append(
                {
                    "type": "tool_result",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
            )
        elif isinstance(msg, dict) and msg.get("type") == "tool":
            history.append(
                {
                    "type": "tool_result",
                    "tool_call_id": msg.get("tool_call_id"),
                    "content": msg.get("content"),
                }
            )
    return history


__all__ = [
    "ChatRunResult",
    "ChatRunnerProtocol",
    "LangGraphRunner",
    "UnconfiguredRunner",
]
