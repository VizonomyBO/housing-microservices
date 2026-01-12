from __future__ import annotations

import re
from datetime import datetime
from typing import Any

YEAR_PATTERN = re.compile(r"(?<!\d)(1[5-9]\d{2}|20\d{2}|21\d{2})(?!\d)")
MIN_PUBLICATION_YEAR = 1500
MAX_PUBLICATION_YEAR = datetime.now().year + 1


def _is_valid_year(year: int) -> bool:
    return MIN_PUBLICATION_YEAR <= year <= MAX_PUBLICATION_YEAR


def coerce_publication_year(value: Any) -> int | None:
    """Convert a loose value (int/float/str) into a validated publication year.

    Accepts 4-digit years between MIN_PUBLICATION_YEAR and MAX_PUBLICATION_YEAR.
    Strings may contain extra characters; the first 4-digit year match is used.
    Returns None when no valid year can be derived.
    """

    if value is None:
        return None

    candidate: int | None = None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = value
    elif isinstance(value, float) and value.is_integer():
        candidate = int(value)
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.isdigit():
            candidate = int(normalized)
        else:
            match = YEAR_PATTERN.search(normalized)
            if match:
                group_value = match.group(1) if match.lastindex else match.group(0)
                candidate = int(group_value)

    if candidate is None:
        return None
    if not _is_valid_year(candidate):
        return None
    return candidate


def extract_years_from_text(text: str | None) -> list[int]:
    """Return sorted, unique publication year candidates from a text blob."""

    if not text:
        return []

    candidates: set[int] = set()
    for raw in YEAR_PATTERN.findall(text):
        try:
            year = int(raw)
        except (TypeError, ValueError):
            continue
        if _is_valid_year(year):
            candidates.add(year)
    return sorted(candidates)


def normalize_metadata_publication_year(
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], int | None, bool]:
    """Normalize publication_year in metadata and report whether it was provided.

    Returns a (metadata, year, provided_flag) tuple. Invalid/blank values are
    removed from the payload; callers can decide whether to raise or ignore.
    """

    payload = dict(metadata or {})
    provided = "publication_year" in payload
    year = coerce_publication_year(payload.get("publication_year"))
    if year is not None:
        payload["publication_year"] = year
    elif provided:
        payload.pop("publication_year", None)
    return payload, year, provided


__all__ = [
    "coerce_publication_year",
    "extract_years_from_text",
    "normalize_metadata_publication_year",
    "MIN_PUBLICATION_YEAR",
    "MAX_PUBLICATION_YEAR",
    "YEAR_PATTERN",
]
