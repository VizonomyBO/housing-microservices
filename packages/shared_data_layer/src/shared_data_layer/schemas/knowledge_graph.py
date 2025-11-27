from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import field_validator

from .common import ORMBaseSchema


class GraphEvidenceRead(ORMBaseSchema):
    id: UUID
    edge_id: UUID
    chunk_id: Optional[UUID] = None
    chunk_country_code: Optional[str] = None
    offsets: Optional[tuple[int, int]] = None
    confidence: Optional[float] = None
    metadata_: Optional[dict] = None

    @field_validator("offsets", mode="before")
    @classmethod
    def _normalize_offset_range(cls, value: Any) -> Any:
        return cls._range_to_tuple(value)

    @staticmethod
    def _range_to_tuple(value: Any) -> Optional[tuple[int, int]]:
        if value is None or isinstance(value, tuple):
            return value
        lower = getattr(value, "lower", None)
        upper = getattr(value, "upper", None)
        if lower is None or upper is None:
            return None
        return int(lower), int(upper)


class GraphEdgeRead(ORMBaseSchema):
    id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    edge_type: str
    weight: Optional[float] = None
    directional: bool
    metadata_: Optional[dict] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    evidence: List[GraphEvidenceRead] = []


class GraphEntityRead(ORMBaseSchema):
    id: UUID
    name: str
    entity_type: str
    entity_key: str
    description: Optional[str] = None
    labels: Optional[List[str]] = None
    properties: Optional[dict] = None
    score: Optional[float] = None
    country_code: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    chunk_id: Optional[UUID] = None
    chunk_country_code: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    edges_out: List[GraphEdgeRead] = []
    edges_in: List[GraphEdgeRead] = []


class GraphCommunityRead(ORMBaseSchema):
    id: UUID
    community_key: str
    summary: Optional[str] = None
    level: int
    entity_ids: Optional[List[UUID]] = None
    metrics: Optional[dict] = None
    country_code: Optional[str] = None
