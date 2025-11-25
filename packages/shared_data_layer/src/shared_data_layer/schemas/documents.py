from uuid import UUID
from typing import Optional, List
from datetime import datetime

from .common import ORMBaseSchema
from .retrieval import ChunkRead


class ArtifactRead(ORMBaseSchema):
    id: UUID
    artifact_type: str
    s3_uri: str
    byte_size: Optional[int] = None
    content_hash: Optional[str] = None
    metadata_: Optional[dict] = None


class IngestionJobRead(ORMBaseSchema):
    id: UUID
    stage: str
    status: str
    attempt: int
    worker: Optional[str] = None
    last_error: Optional[dict] = None
    trace_id: Optional[UUID] = None


class DocumentRead(ORMBaseSchema):
    id: UUID
    owner_user_id: Optional[UUID] = None
    access_scope: str
    canonical_name: str
    country_code: Optional[str] = None
    language: Optional[str] = None
    tags: Optional[List[str]] = None
    status: str
    ingestion_stage: Optional[str] = None
    content_hash: str
    source_uri: Optional[str] = None
    byte_size: Optional[int] = None
    visibility: Optional[str] = None
    managed_by: Optional[str] = None
    active_chat_refs: int
    metadata_: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class DocumentWithChunksRead(DocumentRead):
    chunks: List[ChunkRead] = []
