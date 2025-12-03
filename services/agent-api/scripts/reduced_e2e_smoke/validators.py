"""Prompt validation helpers driven by the scenario manifest."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from scripts.reduced_e2e_fixtures import DocumentFixture, PromptSpec, ValidationRule


@dataclass(slots=True)
class ValidationSummary:
    passed: bool
    failures: list[str] = field(default_factory=list)
    checks_run: int = 0


def validate_prompt(
    prompt: PromptSpec,
    *,
    answer_text: str,
    done_payload: dict[str, Any] | None,
    expected_document_ids: Iterable[str],
    cited_document_ids: Iterable[str],
    document_fixtures: list[DocumentFixture],
) -> ValidationSummary:
    text = answer_text or ""
    normalized = text.lower()
    failures: list[str] = []
    checks = 0

    expected_docs = {doc_id for doc_id in expected_document_ids if doc_id}
    cited_docs = {doc_id for doc_id in cited_document_ids if doc_id}
    if expected_docs:
        checks += 1
        if not expected_docs.issubset(cited_docs):
            missing = sorted(expected_docs - cited_docs)
            failures.append(f"Missing citations for documents: {', '.join(missing)}")

    for rule in prompt.validation_rules:
        checks += 1
        passed = True
        if rule.type == "regex" and rule.pattern:
            passed = bool(re.search(rule.pattern, text, re.IGNORECASE | re.MULTILINE))
            if not passed:
                failures.append(f"Regex '{rule.pattern}' not found")
        elif rule.type == "keyword" and rule.values:
            missing = [value for value in rule.values if value.lower() not in normalized]
            if missing:
                passed = False
                failures.append(f"Missing keywords: {', '.join(missing)}")
        elif rule.type == "numeric_total" and rule.field:
            passed, message = _validate_numeric_total(
                text,
                rule,
                document_fixtures,
            )
            if not passed and message:
                failures.append(message)
        elif rule.type == "threshold" and rule.value is not None:
            passed = _validate_threshold(text, rule)
            if not passed:
                comparison = rule.comparison or ">="
                failures.append(f"No numeric value met threshold {comparison} {rule.value}")
        else:
            checks -= 1  # ignore unsupported rule and avoid inflating counters

    return ValidationSummary(passed=not failures, failures=failures, checks_run=checks)


def _validate_numeric_total(
    text: str,
    rule: ValidationRule,
    document_fixtures: list[DocumentFixture],
) -> tuple[bool, str | None]:
    tolerance = float(rule.tolerance or 0)
    expected_value = _resolve_expected_value(rule.field, document_fixtures)
    if expected_value is None:
        return True, None
    numbers = _extract_numeric_values(text)
    if not numbers:
        return False, "No numeric values found in response"
    for value in numbers:
        if math.isfinite(value) and abs(value - expected_value) <= tolerance:
            return True, None
    return False, f"No numeric value within ±{tolerance} of {expected_value}"


def _resolve_expected_value(field: str | None, fixtures: list[DocumentFixture]) -> float | None:
    if not field:
        return None
    for fixture in fixtures:
        expectations = fixture.spec.numerical_expectations or {}
        if field in expectations:
            try:
                return float(expectations[field])
            except (TypeError, ValueError):  # pragma: no cover - defensive guard
                return None
        expectations = fixture.spec.kpi_expectations or {}
        if field in expectations:
            try:
                return float(expectations[field])
            except (TypeError, ValueError):
                return None
    return None


def _validate_threshold(text: str, rule: ValidationRule) -> bool:
    if rule.value is None:
        return True
    comparison = (rule.comparison or ">=").strip()
    numbers = _extract_numeric_values(text)
    if not numbers:
        return False
    if comparison == ">":
        return any(value > rule.value for value in numbers)
    if comparison == ">=":
        return any(value >= rule.value for value in numbers)
    if comparison == "<=":
        return any(value <= rule.value for value in numbers)
    if comparison == "<":
        return any(value < rule.value for value in numbers)
    return False


def _extract_numeric_values(text: str) -> list[float]:
    pattern = re.compile(
        r"[$]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(million|m|thousand|k|billion|b)?", re.IGNORECASE
    )
    values: list[float] = []
    for match in pattern.finditer(text):
        raw_value = match.group(1).replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:  # pragma: no cover - defensive guard
            continue
        scale = match.group(2)
        if scale:
            scale = scale.lower()
            if scale in {"m", "million"}:
                value *= 1_000_000
            elif scale in {"k", "thousand"}:
                value *= 1_000
            elif scale in {"b", "billion"}:
                value *= 1_000_000_000
        values.append(value)
    return values


__all__ = ["ValidationSummary", "validate_prompt"]
