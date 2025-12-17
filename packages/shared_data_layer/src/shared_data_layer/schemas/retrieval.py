from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .common import ORMBaseSchema
from .countries import CountryISOAlpha3


class ChunkRead(ORMBaseSchema):
    id: UUID
    document_id: UUID
    position: int
    chunk_type: str
    page_number: Optional[int] = None
    text_content: Optional[str] = None
    image_caption: Optional[str] = None
    schema_summary: Optional[str] = None
    table_payload: Optional[dict] = None
    section_path: Optional[List[str]] = None
    bbox: Optional[dict] = None
    token_count: Optional[int] = None
    artifact_uri: Optional[str] = None
    content_hash: str
    owner_user_id: Optional[UUID] = None
    country_code: Optional[CountryISOAlpha3] = None
    metadata_: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class ChunkMetricsRead(ORMBaseSchema):
    chunk_id: UUID
    chunk_country_code: CountryISOAlpha3
    quality_score: Optional[float] = None
    retrieval_count: int
    last_seen_at: Optional[datetime] = None


class RetrievalRunItemRead(ORMBaseSchema):
    chunk_id: UUID
    chunk_country_code: CountryISOAlpha3
    score: float
    rank: int


class RetrievalRunRead(ORMBaseSchema):
    id: UUID
    query_text: str
    filters: Optional[dict] = None
    document_scope: Optional[dict] = None
    top_k: int
    created_at: datetime
    items: List[RetrievalRunItemRead] = []


class PillarAnswerSourceRead(ORMBaseSchema):
    chunk_id: UUID
    chunk_country_code: CountryISOAlpha3
    contribution_type: str
    weight: float
    evidence_text: str
    page_number: Optional[int] = None


class PillarAnswerRead(ORMBaseSchema):
    id: UUID
    owner_user_id: Optional[UUID] = None
    country_code: CountryISOAlpha3
    pillar_name: str
    document_id: UUID
    content_hash: str
    score: Optional[float] = None
    summary_markdown: str
    answer_json: dict
    status: str
    generated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    sources: List[PillarAnswerSourceRead] = []
