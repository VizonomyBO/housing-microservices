from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from ingestion_service.settings import ALLOWED_VOYAGE_OUTPUT_DIMENSIONS


class UploadInitRequest(BaseModel):
    document_name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(
        ..., description="File extension or content type hint (pdf, docx, etc.)"
    )
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    language: str = Field(default="en", min_length=2, max_length=5)
    tags: list[str] = Field(default_factory=list)
    file_size_bytes: int = Field(..., gt=0)
    access_scope: str = Field(default="user_private")
    callback_url: HttpUrl | None = Field(default=None)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata payload (e.g., publication_year, source hints)",
    )
    trace_id: str | None = None
    output_dimension: int | None = Field(
        default=None,
        description="Requested voyage-context-3 output dimension (256/512/1024/2048). Defaults to server config.",
    )

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        return value.lower()

    @field_validator("access_scope")
    @classmethod
    def validate_access_scope(cls, value: str) -> str:
        allowed = {"user_private", "user_shared", "base"}
        if value not in allowed:
            raise ValueError(f"Invalid access_scope '{value}', expected one of {sorted(allowed)}")
        return value

    @field_validator("output_dimension")
    @classmethod
    def validate_output_dimension(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value not in ALLOWED_VOYAGE_OUTPUT_DIMENSIONS:
            raise ValueError(f"output_dimension must be one of {ALLOWED_VOYAGE_OUTPUT_DIMENSIONS}")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else None


class UploadInfo(BaseModel):
    url: str
    fields: dict[str, str]
    expires_in_sec: int


class UploadInitResponse(BaseModel):
    document_id: UUID
    ingestion_id: UUID
    status: str
    upload: UploadInfo
    message: str


class UploadCompleteResponse(BaseModel):
    document_id: UUID
    ingestion_id: UUID
    status: str
    content_hash: str
    message: str | None = None


class AdminDocumentUploadRead(BaseModel):
    id: UUID
    country_code: str
    filename: str
    storage_uri: str
    byte_size: int
    content_hash: str
    source: str
    uploaded_by: UUID
    verified: bool
    verified_by: UUID | None = None
    verified_at: datetime | None = None
    document_id: UUID | None = None
    reprocess_status: str
    reprocess_error: str | None = None
    reprocess_started_at: datetime | None = None
    reprocess_completed_at: datetime | None = None
    ingestion_progress: dict[str, int] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AdminDocumentUploadResponse(BaseModel):
    upload: AdminDocumentUploadRead


class PaginationMetadata(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_count: int = Field(ge=0)
    has_next: bool


class AdminDocumentUploadListResponse(BaseModel):
    items: list[AdminDocumentUploadRead]
    pagination: PaginationMetadata


class AdminCountryReprocessStatusRead(BaseModel):
    country_code: str
    counts: dict[str, int]
    total: int


class AdminCountryReprocessStatusResponse(BaseModel):
    items: list[AdminCountryReprocessStatusRead]
    count: int
