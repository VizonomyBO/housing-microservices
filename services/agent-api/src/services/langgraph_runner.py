"""LangGraph chat runner wiring HTTP requests to the agent graph."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import polars as pl
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.http.context import AuthContext, RequestContext
from agent_api.http.errors import GatewayError
from agent_api.http.schemas import ResponseMode
from agent_api.http.streaming import ChatRunResult
from agent_api.reduced_scope import ReducedScopeFlags
from cache import ValkeyCacheClientProtocol
from cache.response_serializer import CacheCitation
from guardrails.engine import GuardrailEngine
from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from models.retrieval import AttachmentDocument, ChatRequestContext
from nodes.retrieval import AttachmentScopeLoaderNode, InputNormalizerNode
from nodes.retrieval.exceptions import NodeError
from nodes.retrieval.graph.repository import GraphDataRepository
from nodes.retrieval.graph_retriever_node import GraphRetrieverNode
from nodes.retrieval.graph_summarizer_node import GraphSummarizerNode
from nodes.retrieval.utils.language import LanguageDetectorProtocol
from nodes.router.router_node import RouterNode
from repositories.agent_checkpoint_repository import (
    AgentCheckpointRepository,
    CheckpointSaveOptions,
)
from repositories.conversation_scope_repository import ConversationScopeRepository
from services.answer_composer import OpenAIAnswerComposer
from services.conversation_summary_cache import ConversationSummaryCache
from services.model_clients import OpenAIChatClientProtocol
from services.numerical_fact_extractor import NumericFactExtractor
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
        fact_extractor: NumericFactExtractor | None = None,
        summary_cache: ConversationSummaryCache | None = None,
    ) -> None:
        self._cache_client = cache_client
        self._cache_observability = cache_observability
        self._language_detector = language_detector
        self._answer_composer = OpenAIAnswerComposer(client=openai_client)
        self._router = RouterNode(guardrail_engine=GuardrailEngine())
        self._metrics = metrics
        self._sql_generator = HeuristicSqlGenerator()
        self._fact_extractor = fact_extractor or NumericFactExtractor(client=openai_client)
        self._summary_cache = summary_cache or ConversationSummaryCache(cache_client)

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
        checkpoint_repo = AgentCheckpointRepository(db_session)
        conversation_uuid = self._parse_conversation_uuid(request.conversation_id)
        state, history_count = await self._initialize_state(
            request,
            checkpoint_repo,
            reduced_scope,
            conversation_uuid,
            metrics,
        )
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

        final_state = self._append_assistant_message(final_state)
        persisted_state = await self._persist_run(
            repository=checkpoint_repo,
            state=final_state,
            new_message_start=history_count,
            checkpoint_type="chat_run",
            db_session=db_session,
            conversation_uuid=conversation_uuid,
            request=request,
        )
        payload = self._build_done_payload(request, persisted_state)
        messages = self._build_messages(persisted_state)
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
        return state.model_copy(update=updates)

    async def _run_numerical_pipeline(
        self, state: AgentState, context: RunnerContext
    ) -> AgentState:
        tables = list(state.numerical_tables or [])
        if not tables:
            tables = await self._build_numerical_tables(state)
        if not tables:
            return self._numerical_fallback(
                state, "Numeric prompt but no numerical tables were found"
            )
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

    def _numerical_fallback(self, state: AgentState, message: str) -> AgentState:
        findings = list(state.guardrail_findings)
        findings.append(
            GuardrailViolation(
                code=GuardrailCode.NUMERICAL_SQL,
                severity=GuardrailSeverity.WARNING,
                message=message,
                details={"reason": "missing_tables"},
            )
        )
        error_log = list(state.error_log)
        error_log.append(message)
        updates = {
            "requires_sql": False,
            "guardrail_findings": findings,
            "error_log": error_log,
        }
        return state.model_copy(update=updates)

    async def _build_numerical_tables(self, state: AgentState) -> list[NumericalTable]:
        scope = state.attachment_scope
        if scope is None or not scope.documents:
            return []
        tables: list[NumericalTable] = []
        for document in scope.documents:
            parsed = self._parse_markdown_table(document)
            fact_rows: list[dict[str, Any]] = []
            if parsed is not None:
                headers, rows = parsed
                if rows:
                    column_names = self._normalize_columns(headers)
                    fact_rows = self._rows_from_markdown(column_names, rows)
            if not fact_rows:
                facts = await self._fact_extractor.extract(document)
                fact_rows = [fact.to_row() for fact in facts]
            if not fact_rows:
                continue

            sample_row = fact_rows[0]
            columns = []
            for name, sample_value in sample_row.items():
                data_type = "float" if isinstance(sample_value, (int, float)) else "text"
                columns.append(NumericalTableColumn(name=name, data_type=data_type))

            alias = self._slugify(document.canonical_name or f"table_{len(tables) + 1}")
            chunk_ids = {
                row.get("source_chunk")
                for row in fact_rows
                if isinstance(row, dict) and row.get("source_chunk")
            }
            fallback_chunks = [
                chunk.chunk_id for chunk in (document.chunks or []) if chunk.chunk_id
            ][:1]
            if not chunk_ids:
                chunk_ids = set(fallback_chunks)
            tables.append(
                NumericalTable(
                    table_id=f"tbl-{document.document_id}",
                    table_name=document.canonical_name or "Numerical Table",
                    alias=alias,
                    columns=columns,
                    row_count=len(fact_rows),
                    sample_rows=fact_rows[:5],
                    metadata={
                        "document_ids": [document.document_id],
                        "chunk_ids": sorted(chunk_ids),
                        "rows": fact_rows,
                    },
                )
            )
        return tables

    def _rows_from_markdown(
        self, column_names: list[str], rows: list[list[str]]
    ) -> list[dict[str, Any]]:
        converted_rows: list[dict[str, Any]] = []
        for row_values in rows:
            converted: dict[str, Any] = {}
            for name, value in zip(column_names, row_values, strict=False):
                converted[name] = self._convert_cell_value(value)
            converted_rows.append(converted)
        return converted_rows

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

    def _build_initial_state(
        self,
        request: ChatRequestContext,
        *,
        history: list[MessageSnapshot] | None = None,
    ) -> AgentState:
        messages = list(history or [])
        messages.append(self._user_message(request))
        flags = request.reduced_scope or ReducedScopeFlags()
        return AgentState(
            messages=messages,
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
        payload["answer_metadata"] = dict(state.answer_metadata or {})
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

    async def _initialize_state(
        self,
        request: ChatRequestContext,
        repository: AgentCheckpointRepository,
        reduced_scope: ReducedScopeFlags | None,
        conversation_uuid: UUID | None,
        metrics: MetricsRegistry,
    ) -> tuple[AgentState, int]:
        history: list[MessageSnapshot] = []
        if conversation_uuid is None:
            if not request.allow_stateless:
                raise GatewayError(
                    code="VALIDATION_ERROR",
                    message="conversation_id must be a valid UUID",
                    status_code=400,
                )
            logger.warning(
                "chat.history_fallback_stateless",
                extra={
                    "conversation_id": request.conversation_id,
                    "owner_user_id": request.owner_user_id,
                },
            )
            metrics.record_history_event(
                event="stateless_fallback",
                route=self._route_hint(request),
                message_count=0,
            )
        else:
            hydrated = await repository.load_latest(conversation_uuid)
            if hydrated and hydrated.state and hydrated.state.messages:
                history = list(hydrated.state.messages)
            metrics.record_history_event(
                event="history_loaded",
                route=self._route_hint(request),
                message_count=len(history),
            )
        state = self._build_initial_state(request, history=history)
        # Align reduced-scope flags with the current request in case previous checkpoints differ.
        state = state.model_copy(
            update={"reduced_scope_flags": reduced_scope or ReducedScopeFlags()}
        )
        return state, len(history)

    def _user_message(self, request: ChatRequestContext) -> MessageSnapshot:
        return MessageSnapshot(
            message=HumanMessage(content=request.message.content),
            stored_at=datetime.now(UTC),
            metadata={"role": "user"},
        )

    def _append_assistant_message(self, state: AgentState) -> AgentState:
        messages = list(state.messages or [])
        citations = []
        for citation in state.citations:
            if hasattr(citation, "model_dump"):
                citations.append(citation.model_dump())
            else:
                citations.append(citation)
        messages.append(
            MessageSnapshot(
                message=AIMessage(content=state.answer or ""),
                stored_at=datetime.now(UTC),
                metadata={"role": "assistant", "citations": citations},
            )
        )
        return state.model_copy(update={"messages": messages})

    async def _persist_run(
        self,
        *,
        repository: AgentCheckpointRepository,
        state: AgentState,
        new_message_start: int,
        checkpoint_type: str,
        db_session: AsyncSession,
        conversation_uuid: UUID | None,
        request: ChatRequestContext,
    ) -> AgentState:
        new_messages = list(state.messages or [])[new_message_start:]
        persisted_state = state
        if conversation_uuid is not None:
            if new_messages:
                await repository.append_messages(conversation_uuid, new_messages)
            persisted_state = await repository.save_checkpoint(
                state,
                CheckpointSaveOptions(
                    checkpoint_type=checkpoint_type,
                    metadata={"route": state.route.value if state.route else None},
                ),
            )
        await self._commit(db_session)
        if conversation_uuid is not None and self._summary_cache is not None:
            await self._summary_cache.invalidate(str(conversation_uuid))
        if conversation_uuid is not None:
            logger.info(
                "checkpoint.persist",
                extra={
                    "conversation_id": str(conversation_uuid),
                    "checkpoint_type": checkpoint_type,
                    "message_count": len(new_messages),
                    "route": state.route.value if state.route else self._route_hint(request),
                },
            )
        return persisted_state

    def _parse_conversation_uuid(self, conversation_id: str) -> UUID | None:
        try:
            return UUID(str(conversation_id))
        except (TypeError, ValueError):
            return None

    def _route_hint(self, request: ChatRequestContext) -> str | None:
        try:
            route = (request.hints or {}).get("route")
        except Exception:
            return None
        if route:
            return str(route)
        return None

    async def _commit(self, db_session: AsyncSession) -> None:
        try:
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise


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
