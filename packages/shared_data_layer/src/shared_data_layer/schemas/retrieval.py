from datetime import datetime
from typing import List, Optional
from uuid import UUID

from .common import ORMBaseSchema


class ChunkRead(ORMBaseSchema):
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    token_count: Optional[int] = None
    page_num: Optional[int] = None
    type: str
    artifact_uri: Optional[str] = None
    schema_summary: Optional[str] = None
    metadata_: Optional[dict] = None
    created_at: datetime


class ChunkMetricsRead(ORMBaseSchema):
    chunk_id: UUID
    retrieval_count: int
    last_retrieved_at: Optional[float] = None


class RetrievalRunItemRead(ORMBaseSchema):
    chunk_id: UUID
    score: float
    rank: int


class RetrievalRunRead(ORMBaseSchema):
    id: UUID
    query_text: str
    filters: Optional[dict] = None
    top_k: int
    created_at: datetime
    items: List[RetrievalRunItemRead] = []
