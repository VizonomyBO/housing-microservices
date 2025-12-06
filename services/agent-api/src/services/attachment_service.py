"""Attachment helpers enforcing reduced-scope constraints."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.conversation_scope_repository import (
    ConversationDocumentRecord,
    ConversationScopeRepository,
)


class AttachmentStatus(str, Enum):
    ATTACHED = "ATTACHED"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    NOT_FOUND = "NOT_FOUND"
    DETACHED = "DETACHED"


@dataclass(slots=True)
class AttachmentResult:
    status: AttachmentStatus
    attachment: ConversationDocumentRecord | None = None
    auto_attached: list[str] = field(default_factory=list)
    message: str | None = None


class DocumentNotReadyError(RuntimeError):
    """Raised when a document is still ingesting and cannot be attached."""

    def __init__(self, document_id: UUID, status: str | None, stage: str | None):
        super().__init__("Document is still ingesting")
        self.document_id = document_id
        self.status = status
        self.stage = stage


class AttachmentService:
    """Manages conversation attachments under text-only constraints."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        allowed_chunk_types: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        self._scope_repo = ConversationScopeRepository(session)
        self._document_repo = DocumentRepository(session)
        normalized = tuple(ct.lower() for ct in (allowed_chunk_types or ("text",)))
        self._allowed_chunk_types = normalized or ("text",)

    async def list_attachments(
        self, conversation_id: str | UUID
    ) -> list[ConversationDocumentRecord]:
        return await self._scope_repo.list_conversation_documents(conversation_id)

    async def attach_document(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
        attach_source: str,
        visibility: str | None,
        role: str | None,
        attached_by_user_id: str | UUID | None,
        auto_attach_base_docs: bool = False,
    ) -> AttachmentResult:
        conversation = await self._ensure_conversation(conversation_id)
        document = await self._session.get(Document, _as_uuid(document_id))
        if document is None:
            raise LookupError("Document not found")
        self._ensure_document_ready(document)

        auto_attached = []
        if auto_attach_base_docs:
            auto_attached = await self._auto_attach_base_docs(conversation)

        if await self._has_disallowed_chunks(document.id):
            await self._record_skip_metadata(document, conversation, capability="attachments")
            message = "Non-text attachments are disabled during reduced-scope demo"
            return AttachmentResult(
                status=AttachmentStatus.FEATURE_DISABLED,
                auto_attached=auto_attached,
                message=message,
            )

        record = await self._scope_repo.ensure_attachment(
            conversation_id=conversation.id,
            document_id=document.id,
            attach_source=attach_source,
            role=role or "primary",
            visibility_override=visibility,
            attached_by_user_id=_as_uuid(attached_by_user_id) if attached_by_user_id else None,
        )
        return AttachmentResult(
            status=AttachmentStatus.ATTACHED,
            attachment=record,
            auto_attached=auto_attached,
        )

    async def detach_document(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
    ) -> AttachmentStatus:
        conversation = await self._ensure_conversation(conversation_id)
        document = await self._session.get(Document, _as_uuid(document_id))
        if document is None:
            return AttachmentStatus.NOT_FOUND
        if document.access_scope == "base":
            raise ValueError("Base documents cannot be detached; hide them instead")
        removed = await self._document_repo.detach_from_conversation(
            conversation_id=conversation.id,
            document_id=document.id,
        )
        return AttachmentStatus.DETACHED if removed else AttachmentStatus.NOT_FOUND

    async def _has_disallowed_chunks(self, document_id: UUID) -> bool:
        stmt = (
            select(Chunk.id)
            .where(Chunk.document_id == document_id)
            .where(Chunk.chunk_type.not_in(self._allowed_chunk_types))
            .limit(1)
        )
        row = await self._session.execute(stmt)
        return row.scalar_one_or_none() is not None

    async def _ensure_conversation(self, conversation_id: str | UUID) -> Conversation:
        conversation = await self._scope_repo.fetch_conversation(conversation_id)
        if conversation is None:
            raise LookupError("Conversation not found")
        return conversation

    async def _auto_attach_base_docs(self, conversation: Conversation) -> list[str]:
        if not conversation.country_code:
            return []
        summaries = await self._scope_repo.list_base_documents_for_country(
            conversation.country_code
        )
        attached: list[str] = []
        for summary in summaries:
            if not summary.auto_attach_enabled:
                continue
            doc_uuid = _as_uuid(summary.document_id)
            if await self._has_disallowed_chunks(doc_uuid):
                document = await self._session.get(Document, doc_uuid)
                if document is not None:
                    await self._record_skip_metadata(
                        document,
                        conversation,
                        capability="attachments",
                    )
                continue
            record = await self._scope_repo.ensure_attachment(
                conversation_id=conversation.id,
                document_id=doc_uuid,
                attach_source="base_auto",
            )
            attached.append(record.document_id)
        return attached

    async def _record_skip_metadata(
        self,
        document: Document,
        conversation: Conversation,
        *,
        capability: str,
    ) -> None:
        metadata = dict(document.metadata_ or {})
        reduced_scope_meta = metadata.setdefault("reduced_scope", {})
        skips = reduced_scope_meta.setdefault("skipped", [])
        skips.append(
            {
                "capability": capability,
                "conversation_id": str(conversation.id),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        document.metadata_ = metadata
        await self._session.flush()

    def _ensure_document_ready(self, document: Document) -> None:
        if document.status != "active" or document.ingestion_stage != "activate":
            raise DocumentNotReadyError(document.id, document.status, document.ingestion_stage)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = [
    "AttachmentResult",
    "AttachmentService",
    "AttachmentStatus",
    "DocumentNotReadyError",
]
