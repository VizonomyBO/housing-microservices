"""Dataclasses and enums shared by guardrail validators and the router."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from models.retrieval import AttachmentScope, NormalizedInput


class GuardrailSeverity(str, Enum):
    """Severity levels emitted by guardrail validators."""

    WARNING = "warning"
    ERROR = "error"


class GuardrailCode(str, Enum):
    """Stable guardrail violation identifiers.

    Codes intentionally cover both prompt-level and attachment-level policies so downstream
    components (e.g., HumanGate, SSE telemetry) can bucket violations deterministically.
    """

    PROMPT_INJECTION = "prompt_injection"
    PROMPT_POLICY = "prompt_policy"
    PII = "pii"
    ATTACHMENT_SCOPE = "attachment_scope"
    ATTACHMENT_LIMIT = "attachment_limit"
    COUNTRY_MISMATCH = "country_mismatch"
    WORKFLOW_POLICY = "workflow_policy"
    COMPLIANCE_POLICY = "compliance_policy"


class GuardrailViolation(BaseModel):
    """Single guardrail failure or warning."""

    code: GuardrailCode
    severity: GuardrailSeverity = Field(default=GuardrailSeverity.ERROR)
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class GuardrailResult(BaseModel):
    """Aggregate result emitted by the guardrail engine."""

    passed: bool = True
    violations: list[GuardrailViolation] = Field(default_factory=list)
    evaluated_policies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def blocking_violations(self) -> list[GuardrailViolation]:
        """Return only ERROR-severity violations."""

        return [
            violation
            for violation in self.violations
            if violation.severity == GuardrailSeverity.ERROR
        ]


class GuardrailContext(BaseModel):
    """Inputs required by guardrail validators."""

    normalized_input: NormalizedInput
    attachment_scope: AttachmentScope | None = None


class RouterRoute(str, Enum):
    """Supported downstream routes."""

    INFORMATIONAL = "informational"
    ANALYST = "analyst"
    NUMERICAL = "numerical"
    VISION = "vision"
    ESCALATE = "escalate"


class RouteDecision(BaseModel):
    """Router classification output consumed by downstream nodes."""

    route: RouterRoute
    confidence: float
    next_subgraph: str | None
    reason: str
