from typing import List, Optional
from uuid import UUID

from .common import ORMBaseSchema


class GraphEvidenceRead(ORMBaseSchema):
    id: UUID
    edge_id: UUID
    chunk_id: Optional[UUID] = None
    evidence_text: str
    score: float


class GraphEdgeRead(ORMBaseSchema):
    id: UUID
    source_id: UUID
    target_id: UUID
    relation: str
    weight: float
    evidence: List[GraphEvidenceRead] = []


class GraphEntityRead(ORMBaseSchema):
    id: UUID
    name: str
    type: str
    description: Optional[str] = None
    country_code: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    edges_out: List[GraphEdgeRead] = []
    edges_in: List[GraphEdgeRead] = []


class GraphCommunityRead(ORMBaseSchema):
    id: UUID
    name: str
    description: Optional[str] = None
    level: int
