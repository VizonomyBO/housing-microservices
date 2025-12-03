"""AnswerSynthesizer node for the Informational subgraph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agent_api.reduced_scope import ReducedScopeFlags
from cache.cache_writer import CacheShortCircuitResult, maybe_serve_from_cache
from cache.response_serializer import CacheCitation, CacheWorkflowPlanExcerpt
from cache.valkey_client import ValkeyCacheClientProtocol
from models.retrieval import AttachmentScope
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


__all__ = [
    "AnswerComposerProtocol",
    "AnswerSynthesisContext",
    "AnswerSynthesisError",
    "AnswerSynthesisResult",
    "AnswerSynthesizerNode",
]
