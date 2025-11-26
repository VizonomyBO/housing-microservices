from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from shared_data_layer.db.models.documents import ConversationDocument, Document
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.documents import DocumentRead, DocumentWithChunksRead


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session):
        super().__init__(session, Document)

    async def get_document_with_chunks(
        self, document_id: UUID
    ) -> Optional[DocumentWithChunksRead]:
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.chunks))
        )
        result = await self.session.execute(stmt)
        document = result.unique().scalar_one_or_none()
        if document:
            return DocumentWithChunksRead.model_validate(document)
        return None

    async def list_documents_for_country(
        self, country_code: str, include_base: bool = True
    ) -> List[DocumentRead]:
        stmt = select(Document).where(Document.country_code == country_code)
        # Logic for include_base could be added here if 'base' means something
        # specific in access_scope or similar
        result = await self.session.execute(stmt)
        documents = result.scalars().all()
        return [DocumentRead.model_validate(doc) for doc in documents]

    async def create_or_get_document(
        self, owner_user_id: Optional[UUID], content_hash: str, **kwargs
    ) -> Document:
        """
        Check if a document exists with the given (owner_user_id, content_hash).
        If yes, return it. If no, create a new one.
        """
        stmt = select(Document).where(
            Document.owner_user_id == owner_user_id,
            Document.content_hash == content_hash,
        )
        result = await self.session.execute(stmt)
        existing_doc = result.scalar_one_or_none()

        if existing_doc:
            return existing_doc

        # Create new document
        new_doc = Document(
            owner_user_id=owner_user_id, content_hash=content_hash, **kwargs
        )
        self.session.add(new_doc)
        await self.session.flush()
        await self.session.refresh(new_doc)
        return new_doc

    async def attach_to_conversation(
        self,
        conversation_id: str,
        document_id: UUID,
        attach_source: str,
        role: str = "primary",
        attached_by_user_id: Optional[UUID] = None,
        visibility_override: Optional[str] = None,
    ) -> ConversationDocument:
        """
        Attach a document to a conversation and increment the reference count.
        """
        # Check if already attached
        stmt = select(ConversationDocument).where(
            ConversationDocument.conversation_id == conversation_id,
            ConversationDocument.document_id == document_id,
        )
        result = await self.session.execute(stmt)
        existing_attachment = result.scalar_one_or_none()

        if existing_attachment:
            return existing_attachment

        # Create attachment
        attachment = ConversationDocument(
            conversation_id=conversation_id,
            document_id=document_id,
            attach_source=attach_source,
            role=role,
            attached_by_user_id=attached_by_user_id,
            visibility_override=visibility_override,
        )
        self.session.add(attachment)

        # Increment ref count
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(active_chat_refs=Document.active_chat_refs + 1)
        )

        await self.session.flush()
        await self.session.refresh(attachment)
        return attachment

    async def detach_from_conversation(
        self, conversation_id: str, document_id: UUID
    ) -> bool:
        """
        Detach a document from a conversation and decrement the reference count.
        """
        stmt = select(ConversationDocument).where(
            ConversationDocument.conversation_id == conversation_id,
            ConversationDocument.document_id == document_id,
        )
        result = await self.session.execute(stmt)
        attachment = result.scalar_one_or_none()

        if not attachment:
            return False

        await self.session.delete(attachment)

        # Decrement ref count
        await self.session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(active_chat_refs=Document.active_chat_refs - 1)
        )

        return True
