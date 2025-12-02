"""AnswerSynthesizer node for the Informational subgraph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cache.cache_writer import CacheShortCircuitResult, maybe_serve_from_cache
from cache.response_serializer import CacheCitation, CacheWorkflowPlanExcerpt
from cache.valkey_client import ValkeyCacheClientProtocol
from models.retrieval import AttachmentScope
from state.agent_state import AgentState, GraphContext, GraphSummary, WorkflowPlan


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

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        normalized_input = state.normalized_input
        if normalized_input is None:
            raise AnswerSynthesisError("AnswerSynthesizer requires normalized_input in AgentState")

        cache_result = await maybe_serve_from_cache(
            client=self.cache_client,
            cache_metadata=state.cache_metadata,
        )
        if cache_result.hit and cache_result.payload is not None:
            return self._serialize_cache_hit(state, cache_result)

        context = AnswerSynthesisContext(
            normalized_prompt=normalized_input.normalized_prompt,
            graph_summary=state.graph_summary,
            graph_context=state.graph_context,
            workflow_plan=state.workflow_plan,
            attachment_scope=state.attachment_scope,
        )
        result = await self.composer.compose(context)
        metadata = cache_result.cache_metadata
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
