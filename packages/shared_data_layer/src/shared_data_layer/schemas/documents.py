from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import model_validator

from .common import ORMBaseSchema
from .countries import CountryISOAlpha3
from .retrieval import ChunkRead


class ArtifactRead(ORMBaseSchema):
    id: UUID
    artifact_type: str
    s3_uri: str
    byte_size: Optional[int] = None
    content_hash: str
    page_range: Optional[tuple[int, int]] = None
    metadata_: Optional[dict] = None


class IngestionJobRead(ORMBaseSchema):
    id: UUID
    stage: str
    status: str
    attempt: int
    worker: Optional[str] = None
    last_error: Optional[dict] = None
    trace_id: Optional[UUID] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DocumentRead(ORMBaseSchema):
    id: UUID
    owner_user_id: Optional[UUID] = None
    access_scope: str
    canonical_name: str
    country_code: Optional[CountryISOAlpha3] = None
    language: Optional[str] = None
    tags: Optional[List[str]] = None
    status: str
    ingestion_stage: Optional[str] = None
    ingestion_started_at: Optional[datetime] = None
    ingestion_completed_at: Optional[datetime] = None
    content_hash: str
    source_uri: Optional[str] = None
    byte_size: Optional[int] = None
    visibility: Optional[str] = None
    managed_by: Optional[str] = None
    active_chat_refs: int
    metadata_: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_scope_identity(self) -> "DocumentRead":
        if self.access_scope != "base" and self.owner_user_id is None:
            raise ValueError("owner_user_id is required for non-base documents")
        if self.access_scope == "base" and self.owner_user_id is not None:
            raise ValueError("base documents cannot define owner_user_id")
        return self


class DocumentWithChunksRead(DocumentRead):
    chunks: List[ChunkRead] = []
