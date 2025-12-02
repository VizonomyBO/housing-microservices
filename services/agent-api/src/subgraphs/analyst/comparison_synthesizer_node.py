"""ComparisonSynthesizer node implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cache.cache_writer import CacheWriter
from cache.response_serializer import (
    CacheCitation,
    CacheResponsePayload,
    CacheWorkflowPlanExcerpt,
)
from state.agent_state import (
    AgentState,
    AnalystComparison,
    AnalystPlan,
    AnalystPlanStep,
    ComparisonAttachment,
    GraphSummary,
    WorkflowPlan,
)
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_cache_write, lifecycle_span


class ComparisonSynthesisError(RuntimeError):
    """Raised when the ComparisonSynthesizer cannot proceed."""


@dataclass(slots=True)
class ComparisonSynthesisContext:
    """Inputs provided to the comparison response builder."""

    analyst_plan: AnalystPlan
    workflow_plan: WorkflowPlan | None
    graph_summary: GraphSummary | None
    normalized_prompt: str | None


@dataclass(slots=True)
class ComparisonSynthesisResult:
    """Structured comparison output used to update AgentState."""

    answer_text: str
    citations: list[CacheCitation]
    attachments: list[ComparisonAttachment]
    chunk_ids: list[str]
    quality_score: float | None = None
    model_metadata: dict[str, Any] | None = None
    workflow_excerpt: CacheWorkflowPlanExcerpt | None = None


class ComparisonResponseBuilder(Protocol):
    """Interface implemented by comparison synthesizer strategies."""

    async def build(self, context: ComparisonSynthesisContext) -> ComparisonSynthesisResult: ...


@dataclass(slots=True)
class ComparisonSynthesizerNode:
    """LangGraph node that finalizes analyst comparisons and writes cache entries."""

    builder: ComparisonResponseBuilder
    cache_writer: CacheWriter

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        analyst_plan = state.analyst_plan
        if analyst_plan is None:
            raise ComparisonSynthesisError(
                "ComparisonSynthesizer requires analyst_plan in AgentState"
            )
        normalized_prompt = (
            state.normalized_input.normalized_prompt if state.normalized_input else None
        )
        async with lifecycle_span(
            emitter=sse_emitter,
            node="analyst_comparison_synthesizer",
            subgraph="analyst",
            metadata={"workflow_plan_id": analyst_plan.plan_id},
        ):
            context = ComparisonSynthesisContext(
                analyst_plan=analyst_plan,
                workflow_plan=state.workflow_plan,
                graph_summary=state.graph_summary,
                normalized_prompt=normalized_prompt,
            )
            result = await self.builder.build(context)
            comparison = AnalystComparison(
                conclusion=result.answer_text,
                attachments=list(result.attachments),
                highlights=self._build_highlights(analyst_plan.steps),
            )
            payload = CacheResponsePayload(
                answer_text=result.answer_text,
                citations=result.citations,
                chunk_ids=result.chunk_ids,
                workflow_plan_excerpt=result.workflow_excerpt,
                model_metadata=result.model_metadata or {},
            )
            write_result = await self.cache_writer.write(
                payload=payload,
                cache_metadata=state.cache_metadata,
            )
            if write_result.cache_key:
                await emit_cache_write(
                    sse_emitter,
                    cache_key=write_result.cache_key,
                    ttl_seconds=self.cache_writer.default_ttl_seconds,
                )
                add_metadata(cache_key=write_result.cache_key)
            metrics = dict(state.subgraph_metrics)
            attachment_count = len(comparison.attachments)
            metrics["analyst.comparison.attachments"] = attachment_count
            add_metadata(attachments=attachment_count, quality_score=result.quality_score)
            return {
                "answer": result.answer_text,
                "citations": result.citations,
                "analyst_comparison": comparison,
                "answer_chunk_ids": list(result.chunk_ids),
                "answer_metadata": result.model_metadata or {},
                "quality_score": result.quality_score,
                "cache_metadata": write_result.cache_metadata,
                "subgraph_metrics": metrics,
            }

    def _build_highlights(self, steps: list[AnalystPlanStep]) -> list[str]:
        highlights: list[str] = []
        for step in steps[:3]:
            highlights.append(step.description)
        return highlights


__all__ = [
    "ComparisonResponseBuilder",
    "ComparisonSynthesisContext",
    "ComparisonSynthesisError",
    "ComparisonSynthesisResult",
    "ComparisonSynthesizerNode",
]
