"""MultimodalResponderNode implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cache.cache_writer import CacheWriter
from cache.response_serializer import CacheCitation, CacheResponsePayload
from guardrails.models import GuardrailSeverity, GuardrailViolation
from models.retrieval import AttachmentScope
from state.agent_state import AgentState, GraphContext, VisionFinding
from streaming.sse_emitter import SSEEmitter
from streaming.with_sse import add_metadata, emit_cache_write, emit_demo_mode_event, lifecycle_span

from .vision_router_node import VisionRouterContextMissing


class MultimodalResponderError(RuntimeError):
    """Raised when the responder cannot continue."""


@dataclass(slots=True)
class VisionResponseContext:
    """Inputs surfaced to the response composer."""

    prompt: str | None
    mode: str
    findings: list[VisionFinding]
    graph_context: GraphContext
    attachment_scope: AttachmentScope | None


@dataclass(slots=True)
class VisionResponseResult:
    """Structured response returned by composers."""

    answer_text: str
    citations: list[CacheCitation]
    chunk_ids: list[str]
    quality_score: float | None = None
    model_metadata: dict[str, Any] | None = None
    attachments: list[dict[str, Any]] | None = None


class VisionResponseComposer(Protocol):
    """Adapter for composing multimodal answers."""

    async def compose(self, context: VisionResponseContext) -> VisionResponseResult: ...


@dataclass(slots=True)
class MultimodalResponderNode:
    """Generates multimodal responses, leveraging cache + HITL fallbacks."""

    composer: VisionResponseComposer
    cache_writer: CacheWriter
    human_gate_subgraph: str = "human_gate"

    async def __call__(
        self, state: AgentState, *, sse_emitter: SSEEmitter | None = None
    ) -> dict[str, Any]:
        async with lifecycle_span(
            emitter=sse_emitter,
            node="vision_multimodal_responder",
            subgraph="vision",
        ):
            demo_skip = await self._maybe_skip_for_demo(state, sse_emitter)
            if demo_skip is not None:
                return demo_skip
            if (
                self._has_blocking_guardrail(state.guardrail_findings)
                or not state.guardrails_passed
            ):
                add_metadata(routed_to_hitl=True)
                return self._route_to_human_gate(state)
            context_model = state.vision_context
            if context_model is None:
                raise VisionRouterContextMissing(
                    "VisionRouterNode must populate vision_context before MultimodalResponderNode runs"
                )
            normalized_prompt = (
                state.normalized_input.normalized_prompt if state.normalized_input else None
            )
            composer_context = VisionResponseContext(
                prompt=normalized_prompt,
                mode=context_model.mode,
                findings=list(state.vision_findings),
                graph_context=state.graph_context,
                attachment_scope=state.attachment_scope,
            )
            result = await self.composer.compose(composer_context)
            payload = CacheResponsePayload(
                answer_text=result.answer_text,
                citations=result.citations,
                chunk_ids=result.chunk_ids,
                model_metadata=result.model_metadata or {},
            )
            write_result = await self.cache_writer.write(
                payload=payload,
                cache_metadata=state.cache_metadata,
                state=state,
            )
            if write_result.cache_key:
                await emit_cache_write(
                    sse_emitter,
                    cache_key=write_result.cache_key,
                    ttl_seconds=self.cache_writer.default_ttl_seconds,
                )
                add_metadata(cache_key=write_result.cache_key)
            answer_metadata = dict(result.model_metadata or {})
            if result.attachments:
                answer_metadata["vision_attachments"] = list(result.attachments)
            metrics = dict(state.subgraph_metrics)
            attachments_len = len(result.attachments or [])
            metrics["vision.responder.attachments"] = attachments_len
            metrics["vision.responder.findings"] = len(state.vision_findings)
            add_metadata(
                attachments=attachments_len,
                findings=len(state.vision_findings),
                quality_score=result.quality_score,
            )
            return {
                "answer": result.answer_text,
                "citations": result.citations,
                "answer_chunk_ids": list(result.chunk_ids),
                "answer_metadata": answer_metadata,
                "quality_score": result.quality_score,
                "cache_metadata": write_result.cache_metadata,
                "subgraph_metrics": metrics,
            }

    def _has_blocking_guardrail(self, findings: list[GuardrailViolation]) -> bool:
        return any(violation.severity == GuardrailSeverity.ERROR for violation in findings)

    def _route_to_human_gate(self, state: AgentState) -> dict[str, Any]:
        return {
            "next_subgraph": self.human_gate_subgraph,
            "interrupt_reason": "guardrail_violation",
            "guardrails_passed": False,
            "subgraph_metrics": dict(state.subgraph_metrics),
        }

    async def _maybe_skip_for_demo(
        self, state: AgentState, sse_emitter: SSEEmitter | None
    ) -> dict[str, Any] | None:
        flags = state.reduced_scope_flags
        if not flags.should_skip_capability("vision"):
            return None
        if sse_emitter is not None and flags.emit_demo_events:
            await emit_demo_mode_event(
                sse_emitter,
                capability="vision",
                metadata={"node": "vision_multimodal_responder"},
            )
        add_metadata(reduced_scope_skip=True, capability="vision")
        metrics = dict(state.subgraph_metrics)
        key = "vision.demo_mode_skipped"
        metrics[key] = metrics.get(key, 0) + 1
        return {
            "subgraph_metrics": metrics,
            "guardrails_passed": True,
            "next_subgraph": "informational_subgraph",
        }


__all__ = [
    "MultimodalResponderError",
    "MultimodalResponderNode",
    "VisionResponseComposer",
    "VisionResponseContext",
    "VisionResponseResult",
]
