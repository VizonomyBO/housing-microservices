#!/usr/bin/env python3
"""Validate a generated housing PDF report.

Reads the PDF with pymupdf (fitz), checks all 11 required sections are present,
detects failure/placeholder content, and reports the results as JSON.

Usage:
    python scripts/validate_pdf_report.py <pdf_path> [--country COUNTRY_CODE] [--strict]

Exit codes:
    0  all sections passed
    1  one or more sections failed (or --strict triggered on warnings)
    2  PDF could not be opened / read
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    print(
        json.dumps(
            {
                "error": "pymupdf is not installed. Run: pip install pymupdf",
                "valid": False,
            }
        ),
        file=sys.stderr,
    )
    sys.exit(2)

EXPECTED_SECTIONS: list[tuple[str, str]] = [
    ("1", "Executive Summary"),
    ("2", "Introduction of Purpose and Scope"),
    ("3", "National and Regional Context"),
    ("4", "Housing Sector within the Economy"),
    ("5", "Institutional and Legal Framework"),
    ("6", "Housing Supply"),
    ("7", "Rental Housing"),
    ("8", "Housing Finance"),
    ("9", "Government Housing Programs and Subsidies"),
    ("10", "Supply and Demand Analysis"),
    ("11", "Constraints and Opportunities"),
]

FAILURE_PATTERNS: list[str] = [
    "i'm sorry",
    "i am sorry",
    "couldn't produce a response",
    "could not produce a response",
    "unable to develop an analysis",
    "unable to produce cited answer",
    "no information available",
    "i don't have enough information",
    "i do not have enough information",
]

_CITATION_RE = re.compile(r"\[\d+\]")

MIN_SECTION_CHARS = 100


@dataclass
class SectionResult:
    number: str
    title: str
    status: str
    reasons: list[str] = field(default_factory=list)
    char_count: int = 0
    citation_count: int = 0
    content_preview: str = ""


@dataclass
class ValidationReport:
    pdf_path: str
    country_code: str
    valid: bool
    sections: list[SectionResult]
    total: int
    passed: int
    failed: int
    warnings: int
    summary: str


def _extract_full_text(doc: fitz.Document) -> str:
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text())
    return "\n".join(parts)


def _find_section_text(full_text: str, section_num: str, section_name: str) -> str | None:
    """Return text belonging to the given section (up to the next section header)."""
    pattern = re.compile(
        rf"{re.escape(section_num)}\.\s+{re.escape(section_name)}",
        re.IGNORECASE,
    )
    match = pattern.search(full_text)
    if match is None:
        return None

    start = match.end()

    next_section_pattern = re.compile(r"\n\d{1,2}\.\s+[A-Z]", re.MULTILINE)
    next_match = next_section_pattern.search(full_text, start)
    end = next_match.start() if next_match else len(full_text)

    return full_text[start:end].strip()


def _detect_failure(text: str) -> list[str]:
    reasons: list[str] = []
    lower = text.lower()
    for pattern in FAILURE_PATTERNS:
        if pattern in lower:
            reasons.append(f"failure pattern: '{pattern}'")
    return reasons


def validate_pdf(pdf_path: Path, country_code: str, strict: bool) -> ValidationReport:
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF '{pdf_path}': {exc}") from exc

    full_text = _extract_full_text(doc)
    doc.close()

    results: list[SectionResult] = []

    for num, title in EXPECTED_SECTIONS:
        result = SectionResult(number=num, title=title, status="passed")
        section_text = _find_section_text(full_text, num, title)

        if section_text is None:
            result.status = "failed"
            result.reasons.append("section title not found in PDF")
            results.append(result)
            continue

        result.char_count = len(section_text)
        result.citation_count = len(_CITATION_RE.findall(section_text))
        result.content_preview = section_text[:150].replace("\n", " ")

        failure_reasons = _detect_failure(section_text)
        if failure_reasons:
            result.status = "failed"
            result.reasons.extend(failure_reasons)
        elif result.char_count < MIN_SECTION_CHARS:
            result.status = "warning"
            result.reasons.append(
                f"content very short ({result.char_count} chars, min {MIN_SECTION_CHARS})"
            )
        elif result.citation_count == 0:
            result.status = "warning"
            result.reasons.append("no citations found — section may lack evidence")

        results.append(result)

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    warnings = sum(1 for r in results if r.status == "warning")

    is_valid = failed == 0 and (not strict or warnings == 0)

    summary_parts: list[str] = [
        f"{len(results)} sections checked",
        f"{passed} passed",
        f"{failed} failed",
        f"{warnings} warnings",
    ]
    if not is_valid:
        failing = [r.title for r in results if r.status == "failed"]
        warning_titles = [r.title for r in results if r.status == "warning"]
        if failing:
            summary_parts.append(f"FAILED: {', '.join(failing)}")
        if warning_titles and strict:
            summary_parts.append(f"WARNINGS (strict): {', '.join(warning_titles)}")

    return ValidationReport(
        pdf_path=str(pdf_path),
        country_code=country_code,
        valid=is_valid,
        sections=results,
        total=len(results),
        passed=passed,
        failed=failed,
        warnings=warnings,
        summary="; ".join(summary_parts),
    )


def _section_result_to_dict(r: SectionResult) -> dict:
    return asdict(r)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a generated housing PDF report for completeness and quality."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to validate")
    parser.add_argument(
        "--country",
        default="",
        metavar="COUNTRY_CODE",
        help="Country code (informational, used in report output)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings (short content, missing citations) as failures",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(
            json.dumps({"error": f"File not found: {pdf_path}", "valid": False}),
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        report = validate_pdf(pdf_path, country_code=args.country or pdf_path.stem, strict=args.strict)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc), "valid": False}), file=sys.stderr)
        sys.exit(2)

    output = {
        "pdf_path": report.pdf_path,
        "country_code": report.country_code,
        "valid": report.valid,
        "summary": report.summary,
        "counts": {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "warnings": report.warnings,
        },
        "sections": [_section_result_to_dict(s) for s in report.sections],
    }

    print(json.dumps(output, indent=2))
    sys.exit(0 if report.valid else 1)


if __name__ == "__main__":
    main()
