"""LangGraph chat runner wiring HTTP requests to the agent graph."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import polars as pl
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
from models.retrieval import AttachmentDocument, ChatRequestContext
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
from state.agent_state import (
    AgentState,
    MessageSnapshot,
    NumericalTable,
    NumericalTableColumn,
)
from streaming.sse_emitter import SSEEmitter
from subgraphs.informational.answer_synthesizer_node import AnswerSynthesizerNode
from subgraphs.numerical import PolarsExecutorNode, ResultValidatorNode, TextToSQLNode
from subgraphs.numerical.text_to_sql_node import (
    SqlGenerationRequest,
    SqlGenerationResult,
    SqlGeneratorProtocol,
)
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
        self._sql_generator = HeuristicSqlGenerator()

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
        if state.requires_sql:
            state = await self._run_numerical_pipeline(state, context)
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
        next_state = state.model_copy(update=updates)
        if next_state.requires_sql:
            tables = self._build_numerical_tables(next_state)
            if not tables:
                logger.warning(
                    "Router requested numerical mode but no tables are available; falling back to text answer",
                    extra={"conversation_id": context.chat_request.thread_id},
                )
                next_state = next_state.model_copy(update={"requires_sql": False})
        return next_state

    async def _run_numerical_pipeline(
        self, state: AgentState, context: RunnerContext
    ) -> AgentState:
        tables = self._build_numerical_tables(state)
        if not tables:
            raise NodeError(code="NUMERICAL_TABLE_MISSING", message="No numerical tables available")
        state = state.model_copy(
            update={
                "numerical_tables": tables,
                "numerical_selected_table": tables[0].alias,
            }
        )

        text_node = TextToSQLNode(generator=self._sql_generator)
        updates = await text_node(state, sse_emitter=context.sse_emitter)
        state = state.model_copy(update=updates)

        executor = PolarsExecutorNode(table_resolver=self._resolve_lazyframes)
        updates = await executor(state, sse_emitter=context.sse_emitter)
        state = state.model_copy(update=updates)

        validator = ResultValidatorNode()
        updates = await validator(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    async def _run_answer(self, state: AgentState, context: RunnerContext) -> AgentState:
        answer_node = AnswerSynthesizerNode(
            composer=self._answer_composer,
            cache_client=self._cache_client,
            cache_observability=self._cache_observability,
        )
        updates = await answer_node(state, sse_emitter=context.sse_emitter)
        return state.model_copy(update=updates)

    def _build_numerical_tables(self, state: AgentState) -> list[NumericalTable]:
        scope = state.attachment_scope
        if scope is None or not scope.documents:
            return []
        tables: list[NumericalTable] = []
        for document in scope.documents:
            parsed = self._parse_markdown_table(document)
            if parsed is None:
                continue
            headers, rows = parsed
            if not rows:
                continue
            column_names = self._normalize_columns(headers)
            converted_rows: list[dict[str, Any]] = []
            for row_values in rows:
                converted: dict[str, Any] = {}
                for name, value in zip(column_names, row_values, strict=False):
                    converted[name] = self._convert_cell_value(value)
                converted_rows.append(converted)
            columns = []
            sample_row = converted_rows[0]
            for name in column_names:
                sample_value = sample_row.get(name)
                columns.append(
                    NumericalTableColumn(
                        name=name,
                        data_type="float" if isinstance(sample_value, (int, float)) else "text",
                    )
                )
            alias = self._slugify(document.canonical_name or f"table_{len(tables) + 1}")
            tables.append(
                NumericalTable(
                    table_id=f"tbl-{document.document_id}",
                    table_name=document.canonical_name or "Numerical Table",
                    alias=alias,
                    columns=columns,
                    row_count=len(converted_rows),
                    sample_rows=converted_rows[:5],
                    metadata={
                        "document_ids": [document.document_id],
                        "chunk_ids": [chunk.chunk_id for chunk in document.chunks][:1],
                        "rows": converted_rows,
                    },
                )
            )
        return tables

    def _parse_markdown_table(
        self, document: AttachmentDocument
    ) -> tuple[list[str], list[list[str]]] | None:
        buffer: list[str] = []
        for chunk in document.chunks or []:
            buffer.append(chunk.text)
        text = "\n".join(buffer)
        lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
        if len(lines) < 2:
            return None
        header = [cell.strip() for cell in lines[0].strip("|").split("|")]
        body_lines = [line for line in lines[2:] if set(line.replace("|", "")).difference("-")]
        rows = []
        for line in body_lines:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != len(header):
                continue
            rows.append(cells)
        if not rows:
            return None
        return header, rows

    def _normalize_columns(self, headers: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: dict[str, int] = {}
        for header in headers:
            base = self._slugify(header)
            count = seen.get(base, 0)
            seen[base] = count + 1
            normalized.append(f"{base}_{count}" if count else base)
        return normalized

    def _convert_cell_value(self, value: str) -> Any:
        stripped = value.strip()
        percent = stripped.endswith("%")
        numeric_token = stripped.rstrip("%")
        if numeric_token.replace(".", "", 1).isdigit():
            number = float(numeric_token)
            if percent:
                return number
            return number if not number.is_integer() else int(number)
        return value.strip()

    def _slugify(self, label: str) -> str:
        tokens = re.sub(r"[^0-9a-zA-Z]+", "_", label).strip("_")
        return tokens.lower() or "table"

    async def _resolve_lazyframes(self, state: AgentState) -> dict[str, pl.LazyFrame]:
        mapping: dict[str, pl.LazyFrame] = {}
        for table in state.numerical_tables:
            rows = table.metadata.get("rows") if table.metadata else None
            if not rows:
                rows = table.sample_rows
            mapping[table.alias] = pl.DataFrame(rows or []).lazy()
        return mapping

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
        requires_sql = bool(state.requires_sql)
        payload: dict[str, Any] = {
            "status": "COMPLETED",
            "answer": answer,
            "thread_id": request.thread_id,
            "route": route,
            "citations": citations,
            "requires_sql": requires_sql,
        }
        if requires_sql:
            trace = dict(state.numerical_trace)
            payload["numerical_trace"] = trace
            payload["sql_queries"] = trace.get("sql_queries", [])
            payload["table_results"] = trace.get("table_results") or list(
                state.numerical_result_rows
            )
            executor = trace.get("executor") or {}
            payload["sql_row_count"] = executor.get("row_count")
        return payload

    def _build_messages(self, state: AgentState) -> list[dict[str, str]]:
        answer = state.answer or ""
        return [{"role": "assistant", "content": answer}]


class HeuristicSqlGenerator(SqlGeneratorProtocol):
    """Deterministic SQL generator used for the numerical subgraph."""

    async def generate(self, request: SqlGenerationRequest) -> SqlGenerationResult:  # type: ignore[override]
        prompt = request.normalized_prompt.lower()
        alias = request.table.alias
        columns = [column.name for column in request.table.columns]
        select_clause = ", ".join(columns)
        query = f"SELECT {select_clause} FROM {alias}"
        threshold = self._extract_threshold(prompt)
        comparator = ">="
        if threshold is not None:
            if any(word in prompt for word in ("below", "under", "less than")):
                comparator = "<="
            query += f" WHERE value {comparator} {threshold}"
        if threshold is not None or "order" in prompt or "exceed" in prompt:
            query += " ORDER BY value DESC"
        return SqlGenerationResult(
            sql=query,
            tables=[alias],
            columns={alias: columns},
            reasoning="heuristic_numerical_planner",
            table_specs=[{"table_id": request.table.table_id}],
            sql_queries=[query],
        )

    def _extract_threshold(self, prompt: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)", prompt)
        if not match:
            return None
        value = float(match.group(1))
        return value if not math.isnan(value) else None


__all__ = ["LangGraphChatRunner", "RunnerContext"]
