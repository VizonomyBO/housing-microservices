"""Helpers for interrogating/maintaining conversation attachment scope."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast, runtime_checkable
from uuid import UUID

from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import ConversationDocument, Document
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class ConversationDocumentRecord:
    """Lightweight projection of conversation_documents joined with documents."""

    document_id: str
    attach_source: str
    role: str
    visibility: Literal["visible", "hidden", "read_only"]
    canonical_name: str | None
    access_scope: str
    country_code: str | None
    metadata: dict[str, Any] | None

    @property
    def read_only(self) -> bool:
        return self.visibility == "read_only"

    @property
    def is_visible(self) -> bool:
        return self.visibility != "hidden"


@dataclass(slots=True)
class DocumentSummary:
    """Summary details required by retrieval scope loaders."""

    document_id: str
    canonical_name: str | None
    access_scope: str
    country_code: str | None
    language: str | None
    status: str
    tags: list[str] | None
    metadata: dict[str, Any] | None

    @property
    def auto_attach_enabled(self) -> bool:
        metadata = self.metadata or {}
        return metadata.get("auto_attach_enabled", True)


@dataclass(slots=True)
class DocumentChunkPreview:
    """Trimmed chunk content surfaced to AttachmentScopeLoader."""

    document_id: str
    chunk_id: str
    text: str
    page_number: int | None = None
    position: int | None = None


class ConversationScopeRepository:
    """Query + mutation helpers around attachment scope."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._document_repo = DocumentRepository(session)

    async def fetch_conversation(self, conversation_id: str | UUID) -> Conversation | None:
        return await self._session.get(Conversation, _as_uuid(conversation_id))

    async def list_conversation_documents(
        self, conversation_id: str | UUID
    ) -> list[ConversationDocumentRecord]:
        stmt = (
            select(
                ConversationDocument.document_id,
                ConversationDocument.attach_source,
                ConversationDocument.role,
                ConversationDocument.visibility_override,
                Document.canonical_name,
                Document.access_scope,
                Document.country_code,
                Document.metadata_,
            )
            .join(Document, Document.id == ConversationDocument.document_id)
            .where(ConversationDocument.conversation_id == _as_uuid(conversation_id))
            .where(ConversationDocument.deleted_at.is_(None))
        )
        rows = await self._session.execute(stmt)
        records: list[ConversationDocumentRecord] = []
        for row in rows:
            raw_visibility = row.visibility_override or "visible"
            visibility = cast(Literal["visible", "hidden", "read_only"], raw_visibility)
            records.append(
                ConversationDocumentRecord(
                    document_id=str(row.document_id),
                    attach_source=row.attach_source,
                    role=row.role,
                    visibility=visibility,
                    canonical_name=row.canonical_name,
                    access_scope=row.access_scope,
                    country_code=row.country_code,
                    metadata=row.metadata_,
                )
            )
        return records

    async def ensure_attachment(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
        attach_source: str,
        role: str = "primary",
        visibility_override: str | None = None,
        attached_by_user_id: str | UUID | None = None,
    ) -> ConversationDocumentRecord:
        attachment = await self._document_repo.attach_to_conversation(
            conversation_id=_as_uuid(conversation_id),
            document_id=_as_uuid(document_id),
            attach_source=attach_source,
            role=role,
            attached_by_user_id=_as_uuid(attached_by_user_id) if attached_by_user_id else None,
            visibility_override=visibility_override,
        )
        document = await self._document_repo.get(_as_uuid(document_id))
        metadata = document.metadata_ if document else None
        raw_visibility = attachment.visibility_override or "visible"
        visibility = cast(Literal["visible", "hidden", "read_only"], raw_visibility)
        return ConversationDocumentRecord(
            document_id=str(attachment.document_id),
            attach_source=attachment.attach_source,
            role=attachment.role,
            visibility=visibility,
            canonical_name=document.canonical_name if document else None,
            access_scope=document.access_scope if document else "user_private",
            country_code=document.country_code if document else None,
            metadata=metadata,
        )

    async def list_base_documents_for_country(
        self,
        country_code: str,
        *,
        status_allowlist: Sequence[str] = ("active",),
    ) -> list[DocumentSummary]:
        stmt = (
            select(Document)
            .where(Document.access_scope == "base")
            .where(Document.country_code == country_code)
            .where(Document.status.in_(status_allowlist))
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._map_document(row) for row in rows]

    async def hydrate_documents(
        self, document_ids: Iterable[str | UUID]
    ) -> dict[str, DocumentSummary]:
        uuids = [_as_uuid(doc_id) for doc_id in document_ids]
        if not uuids:
            return {}
        stmt = select(Document).where(Document.id.in_(uuids))
        rows = (await self._session.execute(stmt)).scalars().all()
        return {str(row.id): self._map_document(row) for row in rows}

    async def load_document_chunk_previews(
        self,
        document_ids: Iterable[str | UUID],
        *,
        chunk_types: Sequence[str] = ("text",),
        max_chars_per_doc: int = 1600,
        max_chunks_per_doc: int = 5,
    ) -> dict[str, list[DocumentChunkPreview]]:
        uuids = [_as_uuid(doc_id) for doc_id in document_ids]
        if not uuids:
            return {}
        stmt = (
            select(
                Chunk.document_id,
                Chunk.id,
                Chunk.position,
                Chunk.text_content,
                Chunk.page_number,
                Chunk.chunk_type,
            )
            .where(Chunk.document_id.in_(uuids))
            .order_by(Chunk.document_id, Chunk.position)
        )
        if chunk_types:
            stmt = stmt.where(Chunk.chunk_type.in_(tuple(chunk_types)))
        rows = await self._session.execute(stmt)
        previews: dict[str, list[DocumentChunkPreview]] = {}
        char_counts: dict[str, int] = {}
        chunk_counts: dict[str, int] = {}
        for row in rows:
            doc_id = str(row.document_id)
            text = (row.text_content or "").strip()
            if not text:
                continue
            if chunk_counts.get(doc_id, 0) >= max_chunks_per_doc:
                continue
            remaining = max_chars_per_doc - char_counts.get(doc_id, 0)
            if remaining <= 0:
                continue
            snippet = text if len(text) <= remaining else text[:remaining]
            previews.setdefault(doc_id, []).append(
                DocumentChunkPreview(
                    document_id=doc_id,
                    chunk_id=str(row.id),
                    text=snippet,
                    page_number=row.page_number,
                    position=row.position,
                )
            )
            char_counts[doc_id] = char_counts.get(doc_id, 0) + len(snippet)
            chunk_counts[doc_id] = chunk_counts.get(doc_id, 0) + 1
        return previews

    def _map_document(self, document: Document) -> DocumentSummary:
        metadata = document.metadata_ if document is not None else None
        return DocumentSummary(
            document_id=str(document.id),
            canonical_name=document.canonical_name,
            access_scope=document.access_scope,
            country_code=document.country_code,
            language=document.language,
            status=document.status,
            tags=document.tags,
            metadata=metadata,
        )


@runtime_checkable
class ConversationScopePort(Protocol):
    async def list_conversation_documents(
        self, conversation_id: str | UUID
    ) -> list[ConversationDocumentRecord]: ...

    async def list_base_documents_for_country(
        self,
        country_code: str,
        *,
        status_allowlist: Sequence[str] = ("active",),
    ) -> list[DocumentSummary]: ...

    async def ensure_attachment(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
        attach_source: str,
        role: str = "primary",
        visibility_override: str | None = None,
        attached_by_user_id: str | UUID | None = None,
    ) -> ConversationDocumentRecord: ...

    async def hydrate_documents(
        self, document_ids: Iterable[str | UUID]
    ) -> dict[str, DocumentSummary]: ...

    async def load_document_chunk_previews(
        self,
        document_ids: Iterable[str | UUID],
        *,
        chunk_types: Sequence[str] = ("text",),
        max_chars_per_doc: int = 1600,
        max_chunks_per_doc: int = 5,
    ) -> dict[str, list[DocumentChunkPreview]]: ...


def _as_uuid(value: str | UUID | None) -> UUID:
    if value is None:
        raise ValueError("Expected UUID value, received None")
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
