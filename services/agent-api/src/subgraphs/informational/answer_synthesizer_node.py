"""AnswerSynthesizer node for the Informational subgraph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agent_api.reduced_scope import ReducedScopeFlags
from cache.cache_writer import CacheShortCircuitResult, maybe_serve_from_cache
from cache.response_serializer import CacheCitation, CacheWorkflowPlanExcerpt
from cache.valkey_client import ValkeyCacheClientProtocol
from models.retrieval import AttachmentScope
from nodes.retrieval.exceptions import NodeError
from state.agent_state import AgentState, GraphContext, GraphSummary, WorkflowPlan
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_cache_hit, emit_cache_miss, lifecycle_span
from telemetry import CacheObservability


class AnswerSynthesisError(RuntimeError):
    """Raised when the AnswerSynthesizer cannot proceed."""


@dataclass(slots=True)
class AnswerSynthesisContext:
    """Inputs surfaced to the answer composer implementation."""

    normalized_prompt: str
    graph_summary: GraphSummary | None
    graph_context: GraphContext
    workflow_plan: WorkflowPlan | None
    attachment_scope: AttachmentScope | None
    reduced_scope_flags: ReducedScopeFlags | None = None


@dataclass(slots=True)
class AnswerSynthesisResult:
    """Structured output returned by the answer composer."""

    answer_text: str
    citations: list[CacheCitation]
    chunk_ids: list[str]
    quality_score: float | None = None
    model_metadata: dict[str, Any] | None = None
    workflow_excerpt: CacheWorkflowPlanExcerpt | None = None


class AnswerComposerProtocol(Protocol):
    """Interface implemented by answer-generation strategies."""

    async def compose(self, context: AnswerSynthesisContext) -> AnswerSynthesisResult: ...


@dataclass(slots=True)
class AnswerSynthesizerNode:
    """LangGraph node that drafts informational answers with cache short-circuiting."""

    composer: AnswerComposerProtocol
    cache_client: ValkeyCacheClientProtocol
    cache_observability: CacheObservability | None = None

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        normalized_input = state.normalized_input
        if normalized_input is None:
            raise AnswerSynthesisError("AnswerSynthesizer requires normalized_input in AgentState")

        async with lifecycle_span(
            emitter=sse_emitter,
            node="informational_answer_synthesizer",
            subgraph="informational",
        ):
            cache_result = await maybe_serve_from_cache(
                client=self.cache_client,
                cache_metadata=state.cache_metadata,
                observability=self.cache_observability,
                state=state,
            )
            if state.requires_sql and cache_result.hit:
                cache_result = CacheShortCircuitResult(
                    cache_metadata=cache_result.cache_metadata,
                    hit=False,
                    payload=None,
                    cache_key=cache_result.cache_key,
                )
                add_metadata(sql_cache_bypass=True)
            if cache_result.cache_key:
                if cache_result.hit:
                    await emit_cache_hit(
                        sse_emitter,
                        cache_key=cache_result.cache_key,
                    )
                else:
                    await emit_cache_miss(
                        sse_emitter,
                        cache_key=cache_result.cache_key,
                        reason="not_found",
                    )
                add_metadata(cache_key=cache_result.cache_key, cache_hit=cache_result.hit)
            if cache_result.hit and cache_result.payload is not None:
                return self._serialize_cache_hit(state, cache_result)

            context = AnswerSynthesisContext(
                normalized_prompt=normalized_input.normalized_prompt,
                graph_summary=state.graph_summary,
                graph_context=state.graph_context,
                workflow_plan=state.workflow_plan,
                attachment_scope=state.attachment_scope,
                reduced_scope_flags=state.reduced_scope_flags,
            )
            result = await self.composer.compose(context)
            metadata = cache_result.cache_metadata
            add_metadata(cache_hit=False)
            if state.requires_sql:
                self._require_numerical_sql_trace(state)
                self._ensure_sql_citation(result, state)
                self._append_sql_rows(result, state)
            return {
                "answer": result.answer_text,
                "citations": result.citations,
                "answer_chunk_ids": list(result.chunk_ids),
                "answer_metadata": result.model_metadata or {},
                "quality_score": result.quality_score,
                "cache_metadata": metadata,
            }

    def _serialize_cache_hit(
        self, state: AgentState, cache_result: CacheShortCircuitResult
    ) -> dict[str, Any]:
        payload = cache_result.payload
        if payload is None:  # pragma: no cover - defensive guard
            raise AnswerSynthesisError("Cache hit lacked payload data")
        metadata = cache_result.cache_metadata
        inferred_score = payload.model_metadata.get("quality_score")
        if inferred_score is None:
            inferred_score = state.quality_score
        return {
            "answer": payload.answer_text,
            "citations": payload.citations,
            "answer_chunk_ids": list(payload.chunk_ids),
            "answer_metadata": payload.model_metadata,
            "quality_score": inferred_score,
            "cache_metadata": metadata,
        }

    def _require_numerical_sql_trace(self, state: AgentState) -> None:
        if not state.requires_sql:
            return
        trace = state.numerical_trace or {}
        sql_queries = trace.get("sql_queries") or []
        executor = trace.get("executor")
        if not sql_queries or executor is None:
            raise NodeError(
                code="NUMERICAL_TRACE_MISSING",
                message="Numeric response rejected: no SQL trace present",
                details={"requires_sql": True},
            )

    def _ensure_sql_citation(self, result: AnswerSynthesisResult, state: AgentState) -> None:
        if any(citation.doc_id == "SQL_RESULT" for citation in result.citations):
            return
        citation = self._build_sql_citation(state)
        result.citations.append(citation)
        if citation.chunk_id not in result.chunk_ids:
            result.chunk_ids.append(citation.chunk_id)
        metadata = dict(result.model_metadata or {})
        sql_meta = dict(metadata.get("sql_trace") or {})
        sql_meta.update(
            {
                "sql_queries": state.numerical_trace.get("sql_queries", []),
                "row_count": state.numerical_trace.get("executor", {}).get("row_count"),
                "table_id": citation.metadata.get("table_id"),
            }
        )
        metadata["sql_trace"] = sql_meta
        result.model_metadata = metadata

    def _build_sql_citation(self, state: AgentState) -> CacheCitation:
        trace = state.numerical_trace or {}
        sql_queries = trace.get("sql_queries") or []
        query = sql_queries[0] if sql_queries else ""
        table_specs = trace.get("table_specs") or [{}]
        table_id = str(table_specs[0].get("table_id") or table_specs[0].get("alias") or "sql")
        executor = trace.get("executor") or {}
        row_count = executor.get("row_count", len(state.numerical_result_rows))
        sample = self._sql_sample_row(state)
        document_ids = table_specs[0].get("document_ids") or []
        chunk_ids = table_specs[0].get("chunk_ids") or []
        snippet_parts = [f"[SQL_RESULT] {table_id} rows={row_count}"]
        if sample:
            snippet_parts.append(f"sample={sample}")
        if query:
            snippet_parts.append(f"query={query[:120]}")
        snippet = " ".join(snippet_parts)
        return CacheCitation(
            doc_id="SQL_RESULT",
            chunk_id=f"{table_id}:sql_result",
            snippet=snippet,
            metadata={
                "sql_query": query,
                "row_count": row_count,
                "table_id": table_id,
                "document_ids": document_ids,
                "chunk_ids": chunk_ids,
            },
        )

    def _sql_sample_row(self, state: AgentState) -> dict[str, Any] | None:
        if state.numerical_result_rows:
            return state.numerical_result_rows[0]
        trace = state.numerical_trace or {}
        table_results = trace.get("table_results") or []
        return table_results[0] if table_results else None

    def _append_sql_rows(self, result: AnswerSynthesisResult, state: AgentState) -> None:
        rows = list(state.numerical_result_rows or [])
        if not rows:
            trace = state.numerical_trace or {}
            rows = list(trace.get("table_results") or [])
        if not rows:
            return
        marker = "[SQL_ROWS]"
        if marker in result.answer_text:
            return
        formatted_rows: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                formatted_rows.append(f"- {row}")
                continue
            parts: list[str] = []
            for key, value in row.items():
                parts.append(f"{key}={value}")
            formatted_rows.append(f"- {', '.join(parts)}")
        rows_block = "\n".join([marker, *formatted_rows])
        result.answer_text = result.answer_text.rstrip() + "\n\n" + rows_block


__all__ = [
    "AnswerComposerProtocol",
    "AnswerSynthesisContext",
    "AnswerSynthesisError",
    "AnswerSynthesisResult",
    "AnswerSynthesizerNode",
]
