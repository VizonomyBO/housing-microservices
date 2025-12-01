from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class GraphFilterContext:
    """Normalized filters derived from AgentState + attachments."""

    scope_hash: str | None
    intent_tags: Sequence[str]
    document_ids: Sequence[str]
    country_codes: Sequence[str]
    owner_user_id: str | None
    refresh_requested: bool = False


@dataclass(slots=True)
class GraphEntityRecord:
    """Raw entity payload returned by the repository."""

    entity_id: str
    label: str
    summary: str | None
    score: float | None
    document_ids: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    country_code: str | None = None
    owner_user_id: str | None = None
    hot_rank: int | None = None
    algo_version: str | None = None


@dataclass(slots=True)
class GraphRelationRecord:
    """Raw relation payload returned by the repository."""

    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    directional: bool
    weight: float | None
    evidence_chunk_ids: list[str]
    evidence_count: int | None
    last_refreshed_at: datetime | None
    metadata: dict[str, object] | None = None


@dataclass(slots=True)
class GraphRetrievalResult:
    """Structured dataset returned by the repository layer."""

    entities: list[GraphEntityRecord] = field(default_factory=list)
    relations: list[GraphRelationRecord] = field(default_factory=list)
    algo_version: str | None = None

    def is_empty(self) -> bool:
        return not self.entities and not self.relations


def unique(sequence: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in sequence:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
