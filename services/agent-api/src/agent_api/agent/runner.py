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
from agent_api.services.retrieval import RetrievalProfile, RetrievalService
from agent_api.services.retrieval_scope import ConversationScopeRepository
from agent_api.settings import Settings
from streaming.events import SSEEventType, TaskLifecyclePayload
from streaming.sse_emitter import SSEEmitter

logger = logging.getLogger(__name__)

_PROFILE_CHAR_LIMIT = 3000
_PROFILE_MAX_TOKENS = 900
_COUNTRY_PROFILE_SYSTEM_PROMPT = (
    "You are a retrieval-first country profile analyst. Use the retrieved evidence to write one or "
    "two concise paragraphs (no bullets or numbered lists) that directly answer the user's "
    "country-focused policy questions. Weave the points together like a textbook section for an "
    "information system: clear topic sentences, coherent flow across sub-questions, and short "
    "sentences when possible. Cite specific facts with [c#] references immediately after each "
    "claim. If retrieval is thin, restate only what is supported. Stay within the response length "
    "limit and never cut off mid-sentence."
)


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
        base_llm_kwargs = {
            "api_key": settings.openai_api_key,
            "model": settings.openai_chat_model,
            "temperature": 0.1,
        }
        self._llm: ChatOpenAI = llm_factory(**base_llm_kwargs)
        self._profile_llm: ChatOpenAI = llm_factory(
            **base_llm_kwargs,
            max_tokens=_PROFILE_MAX_TOKENS,
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
        self._profile_system_prompt = _COUNTRY_PROFILE_SYSTEM_PROMPT
        self._tools = [
            retrieve_documents,
            document_status,
            list_attachments,
            pyodide_sandbox,
            compute_over_chunks,
        ]
        self._agent = build_agent_graph(
            llm=self._llm,
            tools=self._tools,
            system_prompt=self._system_prompt,
        )
        self._profile_agent = build_agent_graph(
            llm=self._profile_llm,
            tools=self._tools,
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
        merged_hints = dict(request.hints or {})
        merged_hints.update(hints or {})
        retrieval_profile = _resolve_retrieval_profile(merged_hints)
        target_country = _resolve_target_country_hint(
            merged_hints, getattr(request, "constraints", None)
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
            metadata={
                "hints": merged_hints,
                "retrieval_profile": retrieval_profile.value,
                "target_country_code": target_country,
            },
            retrieval_profile=retrieval_profile,
            target_country_code=target_country,
            hints=merged_hints,
        )
        set_runtime(runtime)

        convo_service = ConversationService(db_session)
        await convo_service.append_message(
            conversation_id=request.conversation_id,
            role="user",
            content=request.message.model_dump(mode="json"),
        )

        human = HumanMessage(content=request.message.content)
        system_prompt = (
            self._profile_system_prompt
            if retrieval_profile is RetrievalProfile.COUNTRY_PROFILE
            else self._system_prompt
        )
        system = SystemMessage(content=system_prompt)
        config = {"configurable": {"thread_id": request.thread_id}}
        agent = (
            self._profile_agent
            if retrieval_profile is RetrievalProfile.COUNTRY_PROFILE
            else self._agent
        )
        result = await agent.ainvoke({"messages": [system, human]}, config=config)

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
        ai_content = _cap_answer_length(ai_content, _PROFILE_CHAR_LIMIT)

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


def _resolve_retrieval_profile(hints: dict[str, Any]) -> RetrievalProfile:
    if not hints:
        return RetrievalProfile.DEFAULT
    raw_profile = hints.get("retrieval_profile") or hints.get("profile")
    if isinstance(raw_profile, str):
        normalized = raw_profile.strip().lower()
        if normalized in {"country_profile", "report_profile", "report"}:
            return RetrievalProfile.COUNTRY_PROFILE
    for key in ("country_profile", "report_profile"):
        value = hints.get(key)
        if isinstance(value, bool) and value:
            return RetrievalProfile.COUNTRY_PROFILE
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}:
            return RetrievalProfile.COUNTRY_PROFILE
    return RetrievalProfile.DEFAULT


def _resolve_target_country_hint(hints: dict[str, Any], constraints: Any) -> str | None:
    if hints:
        raw = hints.get("country_code")
        if isinstance(raw, str):
            code = raw.strip().upper()
            if code:
                return code
    if constraints and getattr(constraints, "country_code", None):
        code = (constraints.country_code or "").strip().upper()
        if code:
            return code
    return None


def _cap_answer_length(content: str, limit: int) -> str:
    if len(content) <= limit:
        return content
    truncated = content[:limit]
    sentence_breaks = [
        truncated.rfind(". "),
        truncated.rfind("! "),
        truncated.rfind("? "),
        truncated.rfind("\n\n"),
        truncated.rfind("\n"),
    ]
    cutoff = max((pos for pos in sentence_breaks if pos != -1), default=-1)
    if cutoff >= limit // 2:
        truncated = truncated[: cutoff + 1]
    else:
        space_cutoff = truncated.rfind(" ")
        if space_cutoff >= limit // 2:
            truncated = truncated[:space_cutoff]
    truncated = _strip_incomplete_citation(truncated.rstrip())
    return truncated or content[:limit]


def _strip_incomplete_citation(text: str) -> str:
    last_open = text.rfind("[c")
    last_close = text.rfind("]")
    if last_open != -1 and last_open > last_close:
        return text[:last_open].rstrip()
    return text


__all__ = [
    "ChatRunResult",
    "ChatRunnerProtocol",
    "LangGraphRunner",
    "UnconfiguredRunner",
]
