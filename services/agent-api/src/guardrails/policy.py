"""Declarative guardrail policy definitions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from re import Pattern

from guardrails.models import GuardrailCode, GuardrailSeverity


@dataclass(slots=True)
class PromptPolicyRule:
    """Keyword/regex powered prompt rules."""

    name: str
    code: GuardrailCode
    severity: GuardrailSeverity
    description: str
    keywords: tuple[str, ...] = ()
    regexes: tuple[Pattern[str], ...] = ()

    def matches(self, text: str) -> bool:
        lowered = text.lower()
        if any(keyword in lowered for keyword in self.keywords):
            return True
        return any(pattern.search(text) for pattern in self.regexes)


@dataclass(slots=True)
class AttachmentPolicy:
    """Constraints applied to hydrated attachments."""

    max_documents: int = 25
    max_workflows: int = 5
    require_country_match: bool = True
    allow_unknown_country: bool = True
    disallow_hidden: bool = True
    warn_on_read_only: bool = True


@dataclass(slots=True)
class CompliancePolicy:
    """Catch-all compliance filters beyond prompt wording."""

    blocked_topics: tuple[str, ...] = ()
    pii_patterns: tuple[Pattern[str], ...] = ()

    def matches_blocked_topic(self, text: str) -> bool:
        lowered = text.lower()
        return any(topic in lowered for topic in self.blocked_topics)

    def matches_pii(self, text: str) -> Pattern[str] | None:
        for pattern in self.pii_patterns:
            if pattern.search(text):
                return pattern
        return None


@dataclass(slots=True)
class GuardrailPolicy:
    """Root container for all guardrail settings."""

    prompt_rules: tuple[PromptPolicyRule, ...] = field(default_factory=tuple)
    attachment_policy: AttachmentPolicy = field(default_factory=AttachmentPolicy)
    compliance_policy: CompliancePolicy = field(default_factory=CompliancePolicy)


def _compile_patterns(patterns: Iterable[str]) -> tuple[Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


DEFAULT_GUARDRAIL_POLICY = GuardrailPolicy(
    prompt_rules=(
        PromptPolicyRule(
            name="prompt_injection",
            code=GuardrailCode.PROMPT_INJECTION,
            severity=GuardrailSeverity.ERROR,
            description="Detect classic prompt-injection attempts (ignore previous/system, override instructions).",
            keywords=(
                "ignore previous instructions",
                "forget previous instructions",
                "disregard prior directives",
                "act as system",
                "override safety",
                "disable guardrails",
            ),
        ),
        PromptPolicyRule(
            name="restricted_content",
            code=GuardrailCode.PROMPT_POLICY,
            severity=GuardrailSeverity.ERROR,
            description="Block disallowed content requests (credentials, malware).",
            keywords=("password dump", "credential harvest", "exploit", "ransomware"),
        ),
    ),
    attachment_policy=AttachmentPolicy(
        max_documents=30,
        max_workflows=8,
        require_country_match=True,
        allow_unknown_country=True,
        disallow_hidden=True,
        warn_on_read_only=True,
    ),
    compliance_policy=CompliancePolicy(
        blocked_topics=("classified", "top secret"),
        pii_patterns=_compile_patterns(
            (
                r"\b\d{3}-\d{2}-\d{4}\b",  # SSN format
                r"\b\d{16}\b",  # generic 16 digit (credit card) pattern
            )
        ),
    ),
)

__all__ = [
    "DEFAULT_GUARDRAIL_POLICY",
    "AttachmentPolicy",
    "CompliancePolicy",
    "GuardrailPolicy",
    "PromptPolicyRule",
]
