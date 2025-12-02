"""VisionRouterNode implementation."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

from guardrails.models import GuardrailCode, GuardrailSeverity, GuardrailViolation
from state.agent_state import AgentState, VisionAttachmentContext, VisionRouterContext

from .artifacts import extract_vision_attachments


class VisionRouterError(RuntimeError):
    """Raised when the Vision router cannot continue due to missing prerequisites."""


class VisionRouterContextMissing(RuntimeError):
    """Raised when downstream nodes attempt to access a missing Vision context."""


@dataclass(slots=True)
class VisionRouterNode:
    """Classifies image-only vs multimodal vision flows and enforces attachment guardrails."""

    allowed_mime_types: Collection[str] = field(
        default_factory=lambda: {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "image/gif",
            "image/svg+xml",
        }
    )
    sensitive_content_tags: Collection[str] = field(
        default_factory=lambda: {"explicit", "self_harm", "violence"}
    )

    async def __call__(self, state: AgentState) -> dict[str, object]:
        context = self._build_context(state)
        guardrail_findings = self._evaluate_guardrails(context, state.guardrail_findings)
        guardrails_passed = self._guardrails_passed(state.guardrails_passed, guardrail_findings)
        metrics = dict(state.subgraph_metrics)
        metrics["vision.router.attachments"] = len(context.attachments)
        metrics["vision.router.mode"] = context.mode
        metrics["vision.router.warnings"] = len(context.warnings)
        return {
            "vision_context": context,
            "guardrail_findings": guardrail_findings,
            "guardrails_passed": guardrails_passed,
            "subgraph_metrics": metrics,
        }

    def _build_context(self, state: AgentState) -> VisionRouterContext:
        artifacts = extract_vision_attachments(state.attachment_scope)
        if not artifacts:
            raise VisionRouterError("Vision route requires at least one image attachment")
        normalized_prompt = (
            state.normalized_input.normalized_prompt if state.normalized_input else ""
        )
        mode: Literal["image_only", "multimodal"] = (
            "image_only" if not normalized_prompt.strip() else "multimodal"
        )
        warnings: list[str] = []
        attachments: list[VisionAttachmentContext] = []
        for artifact in artifacts:
            attachment = VisionAttachmentContext(
                document_id=artifact.document_id,
                canonical_name=artifact.canonical_name,
                mime_type=artifact.mime_type,
                caption=artifact.caption,
                chunk_id=artifact.chunk_id,
                figure_id=artifact.figure_id,
                content_flags=list(artifact.content_flags),
            )
            attachments.append(attachment)
            if not attachment.caption:
                warnings.append(
                    f"Missing caption metadata for document {attachment.document_id}; "
                    "downstream nodes will rely on fallback descriptions."
                )
        return VisionRouterContext(mode=mode, attachments=attachments, warnings=warnings)

    def _evaluate_guardrails(
        self,
        context: VisionRouterContext,
        existing: list[GuardrailViolation],
    ) -> list[GuardrailViolation]:
        findings = list(existing)
        allowed_mime_types = {mime.lower() for mime in self.allowed_mime_types}
        blocked_tags = {tag.lower() for tag in self.sensitive_content_tags}
        for attachment in context.attachments:
            mime_type = (attachment.mime_type or "").lower()
            if mime_type and mime_type not in allowed_mime_types:
                findings.append(
                    GuardrailViolation(
                        code=GuardrailCode.VISION_MIME_TYPE,
                        severity=GuardrailSeverity.ERROR,
                        message=f"Unsupported vision attachment mime type '{mime_type}'",
                        details={"document_id": attachment.document_id, "mime_type": mime_type},
                    )
                )
            flagged = sorted(
                flag for flag in attachment.content_flags if flag.lower() in blocked_tags
            )
            if flagged:
                findings.append(
                    GuardrailViolation(
                        code=GuardrailCode.VISION_POLICY,
                        severity=GuardrailSeverity.ERROR,
                        message="Sensitive media detected; escalate to HITL.",
                        details={"document_id": attachment.document_id, "flags": flagged},
                    )
                )
        return findings

    def _guardrails_passed(self, current: bool, findings: list[GuardrailViolation]) -> bool:
        if not current:
            return False
        return not any(violation.severity == GuardrailSeverity.ERROR for violation in findings)


__all__ = [
    "VisionRouterContextMissing",
    "VisionRouterError",
    "VisionRouterNode",
]
