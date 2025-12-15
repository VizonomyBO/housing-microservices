"""Deterministic serialization helpers for cache payloads."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CacheCitation(BaseModel):
    """Evidence pointer stored alongside cached answers."""

    model_config = ConfigDict(extra="allow")

    doc_id: str
    chunk_id: str
    snippet: str | None = None
    source_page: str | None = None
    score: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CacheWorkflowPlanExcerpt(BaseModel):
    """Trimmed workflow context cached with answers for downstream subgraphs."""

    plan_id: str | None = None
    version: str | None = None
    steps: list[str] = Field(default_factory=list, description="Ordered short-form steps")
    summary: str | None = None


class CacheResponsePayload(BaseModel):
    """Stable schema describing cached answers."""

    schema_version: int = Field(default=1, ge=1)
    answer_text: str
    citations: list[CacheCitation] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    workflow_plan_excerpt: CacheWorkflowPlanExcerpt | None = None
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


def _sorted_citations(citations: Iterable[CacheCitation]) -> list[dict[str, Any]]:
    return [
        citation.model_dump(mode="json", exclude_none=True)
        for citation in sorted(
            citations,
            key=lambda value: (
                value.doc_id.lower(),
                value.chunk_id.lower(),
                value.snippet or "",
            ),
        )
    ]


def _sorted_chunk_ids(chunk_ids: Iterable[str]) -> list[str]:
    unique_ids = {chunk_id.strip() for chunk_id in chunk_ids if chunk_id}
    return sorted(unique_ids)


def _workflow_excerpt_dict(excerpt: CacheWorkflowPlanExcerpt | None) -> dict[str, Any] | None:
    if excerpt is None:
        return None
    data = excerpt.model_dump(mode="json", exclude_none=True)
    data["steps"] = list(excerpt.steps)
    return data


def serialize_cache_response(payload: CacheResponsePayload) -> bytes:
    """Serialize the payload into canonical JSON bytes."""

    canonical = {
        "schema_version": payload.schema_version,
        "answer_text": payload.answer_text,
        "citations": _sorted_citations(payload.citations),
        "chunk_ids": _sorted_chunk_ids(payload.chunk_ids),
        "workflow_plan_excerpt": _workflow_excerpt_dict(payload.workflow_plan_excerpt),
        "model_metadata": payload.model_metadata,
        "created_at": payload.created_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z"),
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def deserialize_cache_response(data: bytes | str) -> CacheResponsePayload:
    """Hydrate a CacheResponsePayload from serialized JSON bytes."""

    decoded = data.decode("utf-8") if isinstance(data, bytes) else data
    payload = json.loads(decoded)
    return CacheResponsePayload.model_validate(payload)


__all__ = [
    "CacheCitation",
    "CacheResponsePayload",
    "CacheWorkflowPlanExcerpt",
    "deserialize_cache_response",
    "serialize_cache_response",
]
