"""AnswerSynthesizer node for the Informational subgraph."""

from __future__ import annotations

import re
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
    allowed_document_ids: set[str]
    graph_summary: GraphSummary | None
    graph_context: GraphContext
    workflow_plan: WorkflowPlan | None
    attachment_scope: AttachmentScope | None
    reduced_scope_flags: ReducedScopeFlags | None = None
    chat_history: list[dict[str, str]] | None = None


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

            history: list[dict[str, str]] | None = None
            if state.messages:
                history = []
                # Keep a small, recent window to avoid blowing out token budgets.
                for snapshot in list(state.messages)[-10:]:
                    role = (snapshot.metadata or {}).get("role") or snapshot.message.type
                    content = getattr(snapshot.message, "content", None)
                    if not content:
                        continue
                    history.append({"role": str(role or "user"), "content": str(content)})

            explicit_document_ids = {
                ref.document_id
                for ref in normalized_input.attachment_refs
                if ref.document_id and ref.provided_in_request
            }
            scoped_document_ids = explicit_document_ids or {
                ref.document_id for ref in normalized_input.attachment_refs if ref.document_id
            }

            context = AnswerSynthesisContext(
                normalized_prompt=normalized_input.normalized_prompt,
                allowed_document_ids=scoped_document_ids,
                chat_history=history,
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
            inline_mappings = self._normalize_doc_placeholders(result)
            if inline_mappings:
                model_metadata = dict(result.model_metadata or {})
                model_metadata["inline_citations"] = inline_mappings
                result.model_metadata = model_metadata
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
        answer = result.answer_text or ""
        if marker not in answer:
            # Preserve placeholder without emitting inline dumps; table evidence is provided via table_results.
            cleaned = answer.rstrip()
            result.answer_text = f"{cleaned} {marker}".strip()
            return
        result.answer_text = self._strip_inline_sql_rows(answer, marker)

    def _strip_inline_sql_rows(self, answer: str, marker: str) -> str:
        """Remove inline row dumps that may follow the [SQL_ROWS] marker."""
        before, sep, after = answer.partition(marker)
        if not sep:
            return answer
        suffix_lines = after.splitlines()
        cleaned_suffix: list[str] = []
        skipping = True
        for line in suffix_lines:
            stripped = line.strip()
            if skipping and stripped == "":
                continue
            if skipping and stripped.startswith("-"):
                continue
            skipping = False
            cleaned_suffix.append(line)
        cleaned = "\n".join(cleaned_suffix).lstrip()
        base = (before + sep).rstrip()
        if not cleaned:
            return base
        separator = "" if base.endswith((" ", "\n")) else " "
        return f"{base}{separator}{cleaned}"

    def _normalize_doc_placeholders(self, result: AnswerSynthesisResult) -> list[dict[str, Any]]:
        """Convert LLM DOC_* markers into numeric footnotes aligned to citations and surface a mapping."""
        answer = result.answer_text or ""
        pattern = re.compile(r"\[DOC_[A-Za-z0-9_-]+\]")
        matches = list(pattern.finditer(answer))
        if not matches:
            return []

        doc_citations: list[tuple[int, CacheCitation]] = []
        for idx, citation in enumerate(result.citations):
            if citation.doc_id == "SQL_RESULT":
                continue
            doc_citations.append((idx, citation))

        if not doc_citations:
            result.answer_text = pattern.sub("", answer).strip()
            return []

        def _normalized(text: str) -> str:
            cleaned = re.sub(r"^doc[_-]?", "", text, flags=re.IGNORECASE)
            return re.sub(r"[^a-z0-9]+", "", cleaned.lower())

        def _citation_keys(citation: CacheCitation) -> set[str]:
            metadata = citation.metadata or {}
            alias = metadata.get("document_alias")
            raw_keys = [alias, citation.doc_id, citation.chunk_id, metadata.get("citation_key")]
            keys: set[str] = set()
            for raw in raw_keys:
                if not raw:
                    continue
                normalized = _normalized(str(raw))
                if normalized:
                    keys.add(normalized)
            return keys

        inline_mappings: list[dict[str, Any]] = []
        placeholder_map: dict[str, dict[str, Any]] = {}
        key_to_entry: dict[str, dict[str, Any]] = {}
        doc_entries: list[dict[str, Any]] = []

        for footnote, (citation_index, citation) in enumerate(doc_citations, start=1):
            citation.metadata = dict(citation.metadata or {})
            citation.metadata["citation_key"] = (
                citation.metadata.get("citation_key") or f"c{footnote}"
            )
            citation.metadata["footnote"] = footnote
            entry = {
                "citation_index": citation_index,
                "citation": citation,
                "footnote": footnote,
            }
            doc_entries.append(entry)
            for key in _citation_keys(citation):
                key_to_entry.setdefault(key, entry)

        if not doc_entries:
            raise AnswerSynthesisError("No citations available to resolve inline document markers")

        def _replacement(match: re.Match[str]) -> str:
            placeholder_token = match.group(0)
            placeholder = placeholder_token.strip("[]")
            if placeholder in placeholder_map:
                mapping = placeholder_map[placeholder]
                return f"[{mapping['footnote']}]"

            normalized_placeholder = _normalized(placeholder)
            entry = key_to_entry.get(normalized_placeholder)
            if entry is None:
                raise AnswerSynthesisError(
                    f"Inline document placeholder {placeholder_token} does not match any citation"
                )

            citation = entry["citation"]
            footnote = entry["footnote"]
            mapping = {
                "placeholder": placeholder,
                "citation_index": entry["citation_index"],
                "citation_key": citation.metadata.get("citation_key"),
                "footnote": footnote,
            }
            inline_mappings.append(mapping)
            placeholder_map[placeholder] = mapping
            return f"[{footnote}]"

        result.answer_text = pattern.sub(_replacement, answer)
        return inline_mappings


__all__ = [
    "AnswerComposerProtocol",
    "AnswerSynthesisContext",
    "AnswerSynthesisError",
    "AnswerSynthesisResult",
    "AnswerSynthesizerNode",
]
