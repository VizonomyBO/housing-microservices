"""Guardrail engine that evaluates prompt + attachment policies."""

from __future__ import annotations

from collections import Counter

from guardrails.models import (
    GuardrailCode,
    GuardrailContext,
    GuardrailResult,
    GuardrailSeverity,
    GuardrailViolation,
)
from guardrails.policy import DEFAULT_GUARDRAIL_POLICY, GuardrailPolicy


class GuardrailEngine:
    """Executes declarative guardrail policies and returns structured findings."""

    def __init__(self, policy: GuardrailPolicy | None = None):
        self.policy = policy or DEFAULT_GUARDRAIL_POLICY

    def evaluate(self, context: GuardrailContext) -> GuardrailResult:
        result = GuardrailResult(evaluated_policies=["prompt_rules"])
        normalized_prompt = context.normalized_input.normalized_prompt
        raw_prompt = context.normalized_input.raw_prompt

        # Prompt policies
        for rule in self.policy.prompt_rules:
            if rule.matches(normalized_prompt):
                result.violations.append(
                    GuardrailViolation(
                        code=rule.code,
                        severity=rule.severity,
                        message=rule.description,
                        details={"rule": rule.name},
                    )
                )

        # Compliance filters (blocked topics + PII heuristics)
        result.evaluated_policies.append("compliance_policy")
        compliance = self.policy.compliance_policy
        if compliance.matches_blocked_topic(normalized_prompt):
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.COMPLIANCE_POLICY,
                    severity=GuardrailSeverity.ERROR,
                    message="Prompt references blocked topics per compliance policy.",
                )
            )
        pii_pattern = compliance.matches_pii(raw_prompt)
        if pii_pattern is not None:
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.PII,
                    severity=GuardrailSeverity.ERROR,
                    message="Possible PII detected (pattern match).",
                    details={"pattern": pii_pattern.pattern},
                )
            )

        # Attachment constraints
        result.evaluated_policies.append("attachment_policy")
        attachment_scope = context.attachment_scope
        if attachment_scope:
            documents = attachment_scope.documents
            workflows = attachment_scope.workflows
            stats = Counter({"documents": len(documents), "workflows": len(workflows)})
            result.metadata["attachment_counts"] = dict(stats)
            self._evaluate_attachment_limits(documents, workflows, result)
            self._evaluate_attachment_countries(documents, context, result)
            self._capture_read_only_warnings(documents, result)

        result.passed = not result.blocking_violations
        return result

    def _evaluate_attachment_limits(self, documents, workflows, result: GuardrailResult) -> None:
        attachment_policy = self.policy.attachment_policy
        if len(documents) > attachment_policy.max_documents:
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.ATTACHMENT_LIMIT,
                    severity=GuardrailSeverity.ERROR,
                    message="Too many documents attached to the conversation.",
                    details={
                        "max_documents": attachment_policy.max_documents,
                        "actual": len(documents),
                    },
                )
            )
        if len(workflows) > attachment_policy.max_workflows:
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.WORKFLOW_POLICY,
                    severity=GuardrailSeverity.ERROR,
                    message="Too many workflows referenced in the scope.",
                    details={
                        "max_workflows": attachment_policy.max_workflows,
                        "actual": len(workflows),
                    },
                )
            )

    def _evaluate_attachment_countries(
        self, documents, context: GuardrailContext, result: GuardrailResult
    ) -> None:
        attachment_policy = self.policy.attachment_policy
        if not attachment_policy.require_country_match:
            return
        doc_countries = {doc.country_code for doc in documents if doc.country_code}
        doc_countries.discard(None)
        tenant_country = context.normalized_input.tenant_scope.country_code
        if len(doc_countries) > 1:
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.ATTACHMENT_SCOPE,
                    severity=GuardrailSeverity.ERROR,
                    message="Attachments span multiple country partitions.",
                    details={"countries": sorted(doc_countries)},
                )
            )
            return
        if not doc_countries:
            if attachment_policy.allow_unknown_country:
                return
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.COUNTRY_MISMATCH,
                    severity=GuardrailSeverity.ERROR,
                    message="Attachment country metadata missing while policy requires it.",
                )
            )
            return
        doc_country = next(iter(doc_countries))
        if tenant_country and doc_country != tenant_country:
            result.violations.append(
                GuardrailViolation(
                    code=GuardrailCode.COUNTRY_MISMATCH,
                    severity=GuardrailSeverity.ERROR,
                    message="Conversation country does not match attachment country.",
                    details={"document_country": doc_country, "tenant_country": tenant_country},
                )
            )

    def _capture_read_only_warnings(self, documents, result: GuardrailResult) -> None:
        attachment_policy = self.policy.attachment_policy
        if not attachment_policy.warn_on_read_only:
            return
        read_only_docs = [doc.document_id for doc in documents if doc.read_only]
        if read_only_docs:
            result.warnings.append(
                "Read-only documents present: " + ", ".join(sorted(read_only_docs))
            )


__all__ = ["GuardrailEngine"]
