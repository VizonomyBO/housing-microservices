from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import model_validator

from shared_data_layer.config import SYSTEM_OWNER_SENTINEL

from .common import ORMBaseSchema
from .countries import CountryISOAlpha3, Region
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
    country_code: Optional[Union[CountryISOAlpha3, Region]] = None
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
        if self.access_scope == "base":
            if self.owner_user_id not in (None, SYSTEM_OWNER_SENTINEL):
                raise ValueError(
                    "Base documents must omit owner_user_id or use the system owner "
                    "sentinel."
                )
        return self


class DocumentWithChunksRead(DocumentRead):
    chunks: List[ChunkRead] = []


class UploadedFileRead(ORMBaseSchema):
    id: UUID
    document_id: UUID
    owner_user_id: Optional[UUID] = None
    storage_uri: str
    byte_size: int
    content_hash: str
    checksum: Optional[str] = None
    ingestion_metadata: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
