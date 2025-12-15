"""Synchronous ingestion helpers for reduced-scope operation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_data_layer.db.models.documents import Document, IngestionJob
from sqlalchemy.ext.asyncio import AsyncSession


class ReducedScopeCapabilityError(RuntimeError):
    """Raised when a disabled capability is requested during reduced scope."""

    def __init__(self, capability: str, chunk_type: str):
        super().__init__(f"{capability} is disabled for chunk_type='{chunk_type}'")
        self.capability = capability
        self.chunk_type = chunk_type


@dataclass(slots=True)
class IngestionJobSummary:
    """Lightweight view of an ingestion job row."""

    id: UUID
    document_id: UUID
    stage: str
    status: str
    started_at: datetime
    completed_at: datetime


class ReducedScopeIngestionJobService:
    """Creates auto-completed ingestion job rows for text-only uploads."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        allowed_chunk_types: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        normalized = tuple(ct.lower() for ct in (allowed_chunk_types or ("text",)))
        self._allowed_chunk_types = normalized or ("text",)

    def is_chunk_type_allowed(self, chunk_type: str | None) -> bool:
        if chunk_type is None:
            return True
        normalized = chunk_type.lower()
        return normalized in self._allowed_chunk_types

    async def auto_complete(
        self,
        *,
        document_id: UUID,
        chunk_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> IngestionJobSummary:
        """Insert a succeeded ingestion job row and update the document state."""

        if not self.is_chunk_type_allowed(chunk_type):
            raise ReducedScopeCapabilityError("ingestion", chunk_type)

        document = await self._session.get(Document, document_id)
        if document is None:
            raise LookupError(f"Document {document_id} not found")

        now = datetime.now(UTC)
        job = IngestionJob(
            document_id=document_id,
            stage="activate",
            status="succeeded",
            worker="reduced-scope-inline",
            started_at=now,
            completed_at=now,
        )
        self._session.add(job)

        document.status = "active"
        document.ingestion_stage = "activate"
        document.ingestion_started_at = document.ingestion_started_at or now
        document.ingestion_completed_at = now
        document.metadata_ = self._build_metadata_stub(document.metadata_, metadata)

        await self._session.flush()
        await self._session.refresh(job)

        return IngestionJobSummary(
            id=job.id,
            document_id=job.document_id,
            stage=job.stage,
            status=job.status,
            started_at=job.started_at or now,
            completed_at=job.completed_at or now,
        )

    def _build_metadata_stub(
        self,
        existing: dict[str, Any] | None,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = dict(existing or {})
        reduced_scope_meta = metadata.setdefault("reduced_scope", {})
        ingestion_meta = reduced_scope_meta.setdefault("ingestion", {})
        ingestion_meta.setdefault("mode", "text_only")
        ingestion_meta.setdefault("auto_completed", True)
        if extra:
            ingestion_meta.update(extra)
        return metadata


__all__ = [
    "IngestionJobSummary",
    "ReducedScopeCapabilityError",
    "ReducedScopeIngestionJobService",
]
