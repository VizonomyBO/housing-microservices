"""ImageReasonerNode implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from guardrails.models import GuardrailSeverity, GuardrailViolation
from state.agent_state import (
    AgentState,
    VisionAttachmentContext,
    VisionFinding,
    VisionRouterContext,
)

from .vision_router_node import VisionRouterContextMissing


class ImageReasonerError(RuntimeError):
    """Raised when the ImageReasoner cannot proceed."""


@dataclass(slots=True)
class VisionAttachmentPrompt:
    """Prompt-safe attachment metadata forwarded to the analyzer."""

    document_id: str
    caption: str
    chunk_id: str | None
    figure_id: str | None
    mime_type: str | None


@dataclass(slots=True)
class VisionAnalysisContext:
    """Analyzer inputs generated from the router context."""

    prompt: str
    mode: str
    attachments: list[VisionAttachmentPrompt]
    warnings: list[str]


@dataclass(slots=True)
class VisionAnalysisResult:
    """Analyzer outputs consumed by downstream nodes."""

    findings: list[VisionFinding]
    warnings: list[str]
    guardrail_violations: list[GuardrailViolation]
    model_metadata: dict[str, Any] | None = None


class VisionAnalyzerProtocol(Protocol):
    """Interface implemented by multimodal analyzers."""

    async def analyze(self, context: VisionAnalysisContext) -> VisionAnalysisResult: ...


@dataclass(slots=True)
class ImageReasonerNode:
    """Converts image metadata into structured findings via a vision analyzer."""

    analyzer: VisionAnalyzerProtocol

    async def __call__(self, state: AgentState) -> dict[str, object]:
        context = self._ensure_context(state.vision_context)
        normalized_prompt = (
            state.normalized_input.normalized_prompt if state.normalized_input else ""
        )
        warnings = list(context.warnings)
        analysis_context = VisionAnalysisContext(
            prompt=normalized_prompt or "Describe the provided visual attachments.",
            mode=context.mode,
            attachments=self._build_prompts(context, warnings),
            warnings=warnings,
        )
        result = await self.analyzer.analyze(analysis_context)
        error_log = list(state.error_log)
        error_log.extend(analysis_context.warnings)
        error_log.extend(result.warnings)
        guardrail_findings = list(state.guardrail_findings)
        guardrail_findings.extend(result.guardrail_violations)
        guardrails_passed = self._guardrails_passed(state.guardrails_passed, guardrail_findings)
        metrics = dict(state.subgraph_metrics)
        metrics["vision.reasoner.findings"] = len(result.findings)
        if result.model_metadata:
            metrics["vision.reasoner.model"] = result.model_metadata.get("model")
        return {
            "vision_findings": result.findings,
            "guardrail_findings": guardrail_findings,
            "guardrails_passed": guardrails_passed,
            "error_log": error_log,
            "subgraph_metrics": metrics,
        }

    def _ensure_context(self, context: VisionRouterContext | None) -> VisionRouterContext:
        if context is None:
            raise VisionRouterContextMissing(
                "VisionRouterNode must execute before ImageReasonerNode"
            )
        if not context.attachments:
            raise ImageReasonerError("Vision context did not include any attachments")
        return context

    def _build_prompts(
        self,
        context: VisionRouterContext,
        warnings: list[str],
    ) -> list[VisionAttachmentPrompt]:
        prompts: list[VisionAttachmentPrompt] = []
        for index, attachment in enumerate(context.attachments, start=1):
            caption = attachment.caption
            if not caption:
                caption = self._fallback_caption(attachment, index, warnings)
            prompts.append(
                VisionAttachmentPrompt(
                    document_id=attachment.document_id,
                    caption=caption,
                    chunk_id=attachment.chunk_id,
                    figure_id=attachment.figure_id,
                    mime_type=attachment.mime_type,
                )
            )
        return prompts

    def _fallback_caption(
        self,
        attachment: VisionAttachmentContext,
        index: int,
        warnings: list[str],
    ) -> str:
        if attachment.canonical_name:
            fallback = f"{attachment.canonical_name} (image {index})"
        else:
            fallback = f"Image {index} ({attachment.document_id})"
        warnings.append(
            f"Generated fallback caption for document {attachment.document_id}: '{fallback}'"
        )
        return fallback

    def _guardrails_passed(
        self,
        current: bool,
        findings: list[GuardrailViolation],
    ) -> bool:
        if not current:
            return False
        return not any(violation.severity == GuardrailSeverity.ERROR for violation in findings)


__all__ = [
    "ImageReasonerError",
    "ImageReasonerNode",
    "VisionAnalysisContext",
    "VisionAnalysisResult",
    "VisionAnalyzerProtocol",
]
