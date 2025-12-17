"""Attachment management using shared data layer repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy.ext.asyncio import AsyncSession

from agent_api.services.retrieval_scope import (
    ConversationDocumentRecord,
    ConversationScopeRepository,
)


class DocumentNotReadyError(Exception):
    def __init__(self, document_id: UUID, status: str | None, stage: str | None):
        super().__init__("Document not ready")
        self.document_id = document_id
        self.status = status
        self.stage = stage


class AttachmentStatus:
    ATTACHED = "ATTACHED"
    NOT_FOUND = "NOT_FOUND"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    DETACHED = "DETACHED"
    FORBIDDEN = "FORBIDDEN"


@dataclass(slots=True)
class AttachmentResult:
    status: str
    attachment: ConversationDocumentRecord | None = None
    auto_attached: list[str] = field(default_factory=list)
    message: str | None = None


class AttachmentService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._doc_repo = DocumentRepository(session)
        self._scope_repo = ConversationScopeRepository(session)

    async def list_attachments(self, conversation_id: str) -> list[ConversationDocumentRecord]:
        return await self._scope_repo.list_conversation_documents(conversation_id)

    async def attach_document(
        self,
        *,
        conversation_id: str,
        document_id: str,
        attach_source: str,
        visibility: Literal["visible", "hidden", "read_only"] | None,
        role: str | None,
        attached_by_user_id: str | None,
        auto_attach_base_docs: bool = False,  # kept for compatibility
    ) -> AttachmentResult:
        doc = await self._doc_repo.get(UUID(document_id))
        if doc is None:
            raise LookupError("Document not found")
        if doc.status != "active":
            raise DocumentNotReadyError(doc.id, doc.status, doc.ingestion_stage)

        attachment = await self._scope_repo.ensure_attachment(
            conversation_id=conversation_id,
            document_id=document_id,
            attach_source=attach_source,
            role=role or "primary",
            visibility_override=visibility,
            attached_by_user_id=attached_by_user_id,
        )
        return AttachmentResult(
            status=AttachmentStatus.ATTACHED,
            attachment=attachment,
            auto_attached=[],
            message=None,
        )

    async def detach_document(self, *, conversation_id: str, document_id: str) -> str:
        detached = await self._doc_repo.detach_from_conversation(
            conversation_id=UUID(conversation_id),
            document_id=UUID(document_id),
        )
        return AttachmentStatus.DETACHED if detached else AttachmentStatus.NOT_FOUND


__all__ = ["AttachmentResult", "AttachmentService", "AttachmentStatus", "DocumentNotReadyError"]
