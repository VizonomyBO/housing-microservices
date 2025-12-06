from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


class UploadInitRequest(BaseModel):
    document_name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., description="File extension or content type hint (pdf, docx, etc.)")
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    language: str = Field(default="en", min_length=2, max_length=5)
    tags: list[str] = Field(default_factory=list)
    file_size_bytes: int = Field(..., gt=0)
    access_scope: str = Field(default="user_private")
    callback_url: HttpUrl | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None

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

