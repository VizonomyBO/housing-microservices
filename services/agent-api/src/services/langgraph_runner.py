"""LangGraph chat runner wiring HTTP requests to the agent graph."""

from __future__ import annotations

import logging
import math
import json
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
from services.model_clients import (
    OpenAIChatClientProtocol,
    VoyageEmbeddingClientProtocol,
    VoyageRerankClientProtocol,
)
from services.numerical_fact_extractor import NumericFactExtractor
from state.agent_state import (
    AgentState,
    MessageSnapshot,
    NumericalTable,
    NumericalTableColumn,
)
from streaming.sse_emitter import SSEEmitter
from subgraphs.informational.answer_synthesizer_node import AnswerSynthesizerNode
from subgraphs.numerical import (
    PolarsExecutionError,
    PolarsExecutorNode,
    ResultValidatorNode,
    TextToSQLError,
    TextToSQLNode,
)
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
        retrieval_embedding_client: VoyageEmbeddingClientProtocol | None = None,
        retrieval_reranker: VoyageRerankClientProtocol | None = None,
        fact_extractor: NumericFactExtractor | None = None,
        summary_cache: ConversationSummaryCache | None = None,
    ) -> None:
        self._cache_client = cache_client
        self._cache_observability = cache_observability
        self._language_detector = language_detector
        self._answer_composer = OpenAIAnswerComposer(
            client=openai_client, reranker=retrieval_reranker
        )
        self._retrieval_embedding_client = retrieval_embedding_client
        self._retrieval_reranker = retrieval_reranker
        self._router = RouterNode(guardrail_engine=GuardrailEngine())
        self._metrics = metrics
        if openai_client is None:
            raise RuntimeError("OpenAI client is required for numerical planning; no fallback is allowed.")
        self._sql_generator = LlmSqlGenerator(client=openai_client)
        self._fact_extractor = fact_extractor or NumericFactExtractor(client=openai_client)
        self._summary_cache = summary_cache or ConversationSummaryCache(cache_client)
        self._openai_client = openai_client

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
            logger.exception(
                "LangGraph execution failed",
                extra={
                    "conversation_id": request.conversation_id,
                    "thread_id": request.thread_id,
                    "route": self._route_hint(request),
                    "allow_stateless": request.allow_stateless,
                    "hint_keys": list(request.hints.keys()) if request.hints else [],
                },
            )
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
        node = AttachmentScopeLoaderNode(
            scope_repository=scope_repo,
            workflow_repository=None,
            embedding_client=self._retrieval_embedding_client,
            enable_hybrid_search=True,
        )
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
            raise GatewayError(
                code="NUMERICAL_TABLES_MISSING",
                message="Numeric prompt but no numerical tables were built",
                status_code=400,
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
        if self._openai_client is None:
            raise GatewayError(
                code="NUMERICAL_SQL_UNAVAILABLE",
                message="LLM client is required for numerical schema construction",
                status_code=503,
            )
        tables: list[NumericalTable] = []
        for document in scope.documents:
            llm_tables = await self._llm_tables_from_document(document)
            tables.extend(llm_tables)
        return tables

    async def _llm_tables_from_document(self, document: AttachmentDocument) -> list[NumericalTable]:
        text_chunks = [chunk.text for chunk in (document.chunks or []) if chunk.text]
        if not text_chunks:
            return []
        prompt_text = "\n\n".join(text_chunks[:10])
        user_prompt = (
            "Extract structured tables from the document text. "
            "Return JSON with the shape: "
            '{"tables":[{"name":"<table_name>","columns":[{"name":"<col>","type":"number|text"}],"rows":[{"<col>":<value>,...}]}]}. '
            "Use only columns you define; do not invent a 'value' column. "
            "Prefer numeric types when appropriate. Keep row counts small (<=5) and faithful to the source."
            f"\nDocument excerpt:\n{prompt_text}"
        )
        messages = [
            {"role": "system", "content": "You are a data engineer that emits only JSON for tables."},
            {"role": "user", "content": user_prompt},
        ]
        raw = await self._openai_client.complete(messages, temperature=0.0, max_tokens=800)
        try:
            payload = json.loads(raw)
        except Exception:
            logger.error("llm_table_parse_failed", extra={"document_id": document.document_id, "raw": raw[:500]})
            return []
        tables_payload = payload.get("tables") if isinstance(payload, dict) else None
        if not tables_payload or not isinstance(tables_payload, list):
            logger.error("llm_table_missing_tables", extra={"document_id": document.document_id})
            return []

        built: list[NumericalTable] = []
        for idx, table_spec in enumerate(tables_payload):
            if not isinstance(table_spec, dict):
                continue
            name = table_spec.get("name") or document.canonical_name or f"table_{idx+1}"
            alias = self._slugify(f"{name}_{idx+1}")
            columns_spec = table_spec.get("columns") or []
            rows_spec = table_spec.get("rows") or []
            if not columns_spec or not isinstance(columns_spec, list):
                continue
            columns: list[NumericalTableColumn] = []
            name_map: dict[str, str] = {}
            for col in columns_spec:
                if not isinstance(col, dict):
                    continue
                col_name = self._slugify(col.get("name") or "")
                if not col_name:
                    continue
                col_type_raw = (col.get("type") or "").lower()
                col_type = "float" if col_type_raw in {"number", "numeric", "float", "integer"} else "text"
                columns.append(NumericalTableColumn(name=col_name, data_type=col_type))
                name_map[col_name] = col_name
            cleaned_rows: list[dict[str, Any]] = []
            if isinstance(rows_spec, list):
                for row in rows_spec:
                    if isinstance(row, dict):
                        normalized_row: dict[str, Any] = {}
                        for key, value in row.items():
                            slug = self._slugify(str(key))
                            target = name_map.get(slug, slug)
                            normalized_row[target] = value
                        cleaned_rows.append(normalized_row)
            chunk_ids = [
                chunk.chunk_id for chunk in (document.chunks or []) if chunk.chunk_id
            ][:1]
            table = NumericalTable(
                table_id=f"tbl-{document.document_id}-{idx+1}",
                table_name=name,
                alias=alias,
                columns=columns,
                row_count=len(cleaned_rows),
                sample_rows=cleaned_rows[:5],
                metadata={
                    "document_ids": [document.document_id],
                    "chunk_ids": chunk_ids,
                    "rows": cleaned_rows,
                },
            )
            logger.info(
                "numerical.table.built",
                extra={"alias": alias, "columns": [col.name for col in columns], "row_count": len(cleaned_rows)},
            )
            built.append(table)
        return built

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
            logger.info(
                "numerical.lazyframe.rows.sample",
                extra={
                    "alias": table.alias,
                    "columns": list(rows[0].keys()) if rows else [],
                },
            )
            df = pl.DataFrame(rows or [])
            lf = df.lazy()
            logger.info(
                "numerical.lazyframe.schema",
                extra={"alias": table.alias, "columns": lf.columns},
            )
            mapping[table.alias] = lf
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
        if request.allow_stateless or conversation_uuid is None:
            # Stateless runs should not write messages or checkpoints; surface answers only.
            return state

        persisted_state = state
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
        if self._summary_cache is not None:
            await self._summary_cache.invalidate(str(conversation_uuid))
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
        if "amount_usd" in columns:
            value_column = "amount_usd"
        elif "value" in columns:
            value_column = "value"
        else:
            numeric_columns = [
                column.name
                for column in request.table.columns
                if column.data_type == "float"
            ]
            value_column = numeric_columns[0] if numeric_columns else (columns[0] if columns else "value")
        select_clause = ", ".join(columns)
        query = f"SELECT {select_clause} FROM {alias}"
        threshold = self._extract_threshold(prompt)
        comparator = ">="
        if threshold is not None:
            if any(word in prompt for word in ("below", "under", "less than")):
                comparator = "<="
            query += f" WHERE {value_column} {comparator} {threshold}"
        if threshold is not None or "order" in prompt or "exceed" in prompt:
            query += f" ORDER BY {value_column} DESC"
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


class LlmSqlGenerator(SqlGeneratorProtocol):
    """LLM-driven SQL generator that uses the chat client to plan queries."""

    def __init__(self, client: OpenAIChatClientProtocol) -> None:
        self._client = client

    async def generate(self, request: SqlGenerationRequest) -> SqlGenerationResult:  # type: ignore[override]
        if self._client is None:
            raise TextToSQLError("LLM SQL generator requires an OpenAI client")
        table = request.table
        alias = table.alias
        columns = [column.name for column in table.columns]
        sample_rows = table.sample_rows or (table.metadata or {}).get("rows") or []
        row_preview = sample_rows[:3] if isinstance(sample_rows, list) else []
        columns_with_types = ", ".join(
            f"{column.name} ({column.data_type})" for column in request.table.columns
        )

        def prompt(extra_note: str | None = None) -> list[dict[str, str]]:
            user_content = (
                "You are a SQL planner for a Polars SQLContext.\n"
                "- Generate ONE safe SELECT statement for the provided table.\n"
                "- Use ONLY the listed columns; do NOT create new column names.\n"
                "- Keep it simple: filters, ordering, limits. No joins or subqueries.\n"
                "- Prefer numeric columns for comparisons/ordering; if filtering amounts, use 'amount_usd'.\n"
                f"User request: {request.normalized_prompt}\n"
                f"Table alias: {alias}\n"
                f"Columns: {columns_with_types}\n"
                f"Sample rows: {row_preview}\n"
                "Use ONLY the columns listed above. Map any geographic labels to 'city_district' and any money values to 'amount_usd'.\n"
            )
            if extra_note:
                user_content += f"Previous attempt error: {extra_note}\nRegenerate valid SQL."
            return [
                {
                    "role": "system",
                    "content": "Return only SQL. No Markdown, no commentary. Do not invent columns.",
                },
                {"role": "user", "content": user_content},
            ]

        sql = ""
        error_note = None
        for _ in range(5):
            messages = prompt(error_note)
            raw = await self._client.complete(messages, temperature=0.0, max_tokens=256)
            sql = self._extract_sql(raw)
            if not sql:
                error_note = "empty SQL"
                continue
            sql = self._normalize_columns(sql, columns)
            if "value" in sql.lower():
                error_note = (
                    f"query referenced non-existent column 'value'; allowed columns: {', '.join(columns)}"
                )
                continue
            ok, invalid_cols = self._validate_columns(sql, columns, extras=[alias, table.table_id])
            if not ok:
                fixed_sql = self._normalize_columns(sql, columns)
                if fixed_sql != sql:
                    sql = fixed_sql
                    ok, invalid_cols = self._validate_columns(
                        sql, columns, extras=[alias, table.table_id]
                    )
                    if ok:
                        break
                error_note = (
                    f"query referenced invalid columns: {', '.join(invalid_cols)}; allowed: {', '.join(columns)}; last SQL: {sql}"
                )
                sql = ""
                continue
            break
        if not sql:
            raise TextToSQLError(f"LLM SQL generator failed: {error_note or 'empty SQL'}")
        if "value" in sql.lower() and "amount_usd" in columns:
            sql = re.sub(r"(?i)\bvalue\b", "amount_usd", sql)

        return SqlGenerationResult(
            sql=sql,
            tables=[alias],
            columns={alias: columns},
            reasoning="llm_sql_planner",
            table_specs=[{"table_id": table.table_id, "chunk_ids": table.metadata.get("chunk_ids", []) if table.metadata else []}],
            sql_queries=[sql],
        )

    def _extract_sql(self, text: str) -> str:
        fenced = re.findall(r"```(?:sql)?\\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        candidate = fenced[0] if fenced else text
        lines = [line.strip() for line in candidate.splitlines() if line.strip()]
        sql = " ".join(lines)
        # Keep only the first statement.
        if ";" in sql:
            sql = sql.split(";")[0]
        return sql.strip()

    def _normalize_columns(self, sql: str, columns: list[str]) -> str:
        replacements: dict[str, str] = {}
        if "city_district" in columns:
            replacements.update({"district": "city_district", "city": "city_district"})
        if "amount_usd" in columns:
            replacements.update(
                {
                    "amount": "amount_usd",
                    "rental_assistance_q2_1": "amount_usd",
                    "rental_assistance": "amount_usd",
                    "value": "amount_usd",
                }
            )
        if "households_served" in columns:
            replacements["households"] = "households_served"
        for bad, good in replacements.items():
            sql = re.sub(rf"(?i)\\b{re.escape(bad)}\\b", good, sql)
        return sql

    def _validate_columns(
        self, sql: str, allowed: list[str], extras: list[str] | None = None
    ) -> tuple[bool, list[str]]:
        stripped = re.sub(r"'[^']*'", "", sql)
        tokens = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", stripped)
        keywords = {
            "select",
            "from",
            "where",
            "and",
            "or",
            "order",
            "by",
            "desc",
            "asc",
            "limit",
            "group",
            "having",
            "as",
        }
        allowed_set = set(name.lower() for name in allowed)
        if extras:
            allowed_set.update(name.lower() for name in extras)
        invalid: list[str] = []
        for token in tokens:
            lower = token.lower()
            if lower in keywords or lower.isdigit():
                continue
            if lower not in allowed_set:
                invalid.append(token)
        return (len(invalid) == 0, invalid)


__all__ = ["LangGraphChatRunner", "RunnerContext"]
