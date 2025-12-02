"""Document upload helpers enforcing reduced-scope constraints."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import Chunk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestion_job_service import (
    IngestionJobSummary,
    ReducedScopeIngestionJobService,
)


class DocumentUploadStatus(str, Enum):
    COMPLETED = "COMPLETED"
    DEDUPED = "DEDUPED"
    FEATURE_DISABLED = "FEATURE_DISABLED"


@dataclass(slots=True)
class DocumentUploadData:
    document_name: str
    content: str
    content_type: str
    chunk_type: str
    access_scope: str
    country_code: str | None
    language: str | None
    tags: list[str]
    metadata: dict[str, Any]
    owner_user_id: str | None


@dataclass(slots=True)
class DocumentUploadResult:
    status: DocumentUploadStatus
    content_hash: str
    document: Document | None = None
    ingestion_job: IngestionJobSummary | None = None
    message: str | None = None

    @property
    def created(self) -> bool:
        return self.status == DocumentUploadStatus.COMPLETED and self.document is not None


class DocumentUploadService:
    """Handles markitdown text uploads under reduced-scope constraints."""

    def __init__(
        self,
        session: AsyncSession,
        ingestion_service: ReducedScopeIngestionJobService,
        *,
        allowed_chunk_types: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        self._ingestion = ingestion_service
        normalized = tuple(ct.lower() for ct in (allowed_chunk_types or ("text",)))
        self._allowed_chunk_types = normalized or ("text",)

    async def upload_markdown(
        self,
        payload: DocumentUploadData,
    ) -> DocumentUploadResult:
        content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
        chunk_type = payload.chunk_type.lower()
        if chunk_type not in self._allowed_chunk_types:
            return DocumentUploadResult(
                status=DocumentUploadStatus.FEATURE_DISABLED,
                content_hash=content_hash,
                message=f"{payload.chunk_type} ingestion paused during demo mode",
            )

        owner_uuid = self._coerce_owner_uuid(payload.owner_user_id)
        country_code = payload.country_code.upper() if payload.country_code else None
        self._validate_scope(
            access_scope=payload.access_scope, owner_id=owner_uuid, country_code=country_code
        )

        existing = await self._find_existing_document(
            owner_uuid=owner_uuid,
            access_scope=payload.access_scope,
            content_hash=content_hash,
            country_code=country_code,
        )
        if existing:
            return DocumentUploadResult(
                status=DocumentUploadStatus.DEDUPED,
                content_hash=content_hash,
                document=existing,
            )

        document = await self._create_document(
            payload=payload,
            owner_uuid=owner_uuid,
            country_code=country_code,
            content_hash=content_hash,
        )
        await self._create_chunk(
            document=document,
            owner_uuid=owner_uuid,
            country_code=country_code,
            content_hash=content_hash,
            content=payload.content,
        )
        ingestion_summary = await self._ingestion.auto_complete(
            document_id=document.id,
            chunk_type=chunk_type,
            metadata={"source": "document_upload"},
        )
        return DocumentUploadResult(
            status=DocumentUploadStatus.COMPLETED,
            content_hash=content_hash,
            document=document,
            ingestion_job=ingestion_summary,
        )

    def _validate_scope(
        self,
        *,
        access_scope: str,
        owner_id: UUID | None,
        country_code: str | None,
    ) -> None:
        if access_scope == "base":
            if country_code is None:
                raise ValueError("Base documents require a country_code")
            if owner_id is not None:
                raise ValueError("Base documents cannot define owner_user_id")
            return
        if owner_id is None:
            raise ValueError("owner_user_id is required for non-base documents")

    async def _create_document(
        self,
        *,
        payload: DocumentUploadData,
        owner_uuid: UUID | None,
        country_code: str | None,
        content_hash: str,
    ) -> Document:
        now = datetime.now(UTC)
        metadata = self._build_document_metadata(payload.metadata)
        document = Document(
            owner_user_id=owner_uuid,
            access_scope=payload.access_scope,
            canonical_name=payload.document_name,
            country_code=country_code,
            language=payload.language,
            tags=payload.tags or None,
            status="active",
            ingestion_stage="activate",
            ingestion_started_at=now,
            ingestion_completed_at=now,
            content_hash=content_hash,
            byte_size=len(payload.content.encode("utf-8")),
            visibility=self._derive_visibility(payload.access_scope),
            managed_by="system" if payload.access_scope == "base" else "user",
            metadata_=metadata,
        )
        self._session.add(document)
        await self._session.flush()
        await self._session.refresh(document)
        return document

    async def _create_chunk(
        self,
        *,
        document: Document,
        owner_uuid: UUID | None,
        country_code: str | None,
        content_hash: str,
        content: str,
    ) -> None:
        chunk = Chunk(
            document_id=document.id,
            position=0,
            chunk_type="text",
            text_content=content,
            content_hash=content_hash,
            owner_user_id=owner_uuid,
            country_code=country_code or "UNK",
            token_count=self._estimate_tokens(content),
            metadata_={"reduced_scope": {"source": "document_upload"}},
        )
        self._session.add(chunk)

    async def _find_existing_document(
        self,
        *,
        owner_uuid: UUID | None,
        access_scope: str,
        content_hash: str,
        country_code: str | None,
    ) -> Document | None:
        stmt = select(Document).where(Document.content_hash == content_hash)
        stmt = stmt.where(Document.deleted_at.is_(None))
        if access_scope == "base":
            stmt = stmt.where(Document.access_scope == "base")
            stmt = stmt.where(Document.owner_user_id.is_(None))
            if country_code:
                stmt = stmt.where(Document.country_code == country_code)
        else:
            stmt = stmt.where(Document.owner_user_id == owner_uuid)
        row = await self._session.execute(stmt.limit(1))
        return row.scalar_one_or_none()

    def _build_document_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(metadata or {})
        reduced_scope_meta = payload.setdefault("reduced_scope", {})
        reduced_scope_meta["text_only"] = True
        payload.setdefault("source", "markitdown_inline")
        return payload

    @staticmethod
    def _derive_visibility(access_scope: str) -> str:
        if access_scope == "user_shared":
            return "shared"
        if access_scope == "base":
            return "base_admin"
        return "private"

    @staticmethod
    def _estimate_tokens(content: str) -> int:
        word_count = len(content.split()) or 1
        return min(800, word_count)

    @staticmethod
    def _coerce_owner_uuid(value: str | None) -> UUID | None:
        if value is None:
            return None
        return UUID(value)


__all__ = [
    "DocumentUploadData",
    "DocumentUploadResult",
    "DocumentUploadService",
    "DocumentUploadStatus",
]
