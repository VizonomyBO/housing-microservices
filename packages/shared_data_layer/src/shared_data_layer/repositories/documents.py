from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.maintenance import refresh_base_documents_cache
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import (
    ConversationDocument,
    Document,
    UploadedFile,
)
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.documents import (
    DocumentRead,
    DocumentWithChunksRead,
    UploadedFileRead,
)


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
        """
        List documents for a country, including:
        - Country-specific documents (country_code = provided code)
        - Regional documents (country_code = region code for this country)
        - Global documents (country_code = 'GLO')
        """
        from shared_data_layer.schemas.countries import REGION_BY_COUNTRY_ALPHA3, Region

        # Build list of country codes to query
        codes_to_query = [country_code]

        # Add region code if country is mapped
        region = REGION_BY_COUNTRY_ALPHA3.get(country_code)
        if region:
            codes_to_query.append(region.value)

        # Always add global
        codes_to_query.append(Region.GLO.value)

        stmt = select(Document).where(Document.country_code.in_(codes_to_query))
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

        if new_doc.access_scope == "base":
            await self.refresh_base_documents(country_code=new_doc.country_code)

        return new_doc

    async def attach_to_conversation(
        self,
        conversation_id: UUID,
        document_id: UUID,
        attach_source: str,
        role: str = "primary",
        attached_by_user_id: Optional[UUID] = None,
        visibility_override: Optional[str] = None,
    ) -> ConversationDocument:
        """
        Attach a document to a conversation and increment the reference count.
        """
        document = await self.session.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        conversation = await self.session.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        self._validate_attachment_scope(document, conversation)

        # Check if already attached
        stmt = select(ConversationDocument).where(
            ConversationDocument.conversation_id == conversation_id,
            ConversationDocument.document_id == document_id,
        )
        result = await self.session.execute(stmt)
        existing_attachment = result.scalar_one_or_none()

        if existing_attachment:
            if existing_attachment.deleted_at:
                existing_attachment.deleted_at = None
                existing_attachment.attach_source = attach_source
                existing_attachment.role = role
                existing_attachment.visibility_override = visibility_override
                existing_attachment.attached_by_user_id = attached_by_user_id
                await self.session.flush()
            return existing_attachment

        attachment = ConversationDocument(
            conversation_id=conversation_id,
            document_id=document_id,
            attach_source=attach_source,
            role=role,
            attached_by_user_id=attached_by_user_id,
            visibility_override=visibility_override,
        )
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def detach_from_conversation(
        self, conversation_id: UUID, document_id: UUID
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

        if not attachment or attachment.deleted_at:
            return False

        attachment.deleted_at = datetime.now(timezone.utc)
        return True

    async def refresh_base_documents(self, country_code: Optional[str] = None) -> None:
        """
        Refresh the partitioned cache of base documents.
        """
        await refresh_base_documents_cache(self.session, country_code)

    @staticmethod
    def _validate_attachment_scope(
        document: Document,
        conversation: Conversation,
    ) -> None:
        from shared_data_layer.schemas.countries import REGION_BY_COUNTRY_ALPHA3, Region

        if document.access_scope != "base":
            return
        if document.country_code is None:
            raise ValueError(
                "Base documents must define a country_code before attachment."
            )
        if conversation.country_code is None:
            raise ValueError(
                "Conversations must define a country_code "
                "before attaching base documents."
            )

        # Allow exact country match
        if conversation.country_code == document.country_code:
            return

        # Allow global documents for any conversation
        if document.country_code == Region.GLO.value:
            return

        # Allow regional documents if conversation country is in that region
        region = REGION_BY_COUNTRY_ALPHA3.get(conversation.country_code)
        if region and document.country_code == region.value:
            return

        raise ValueError(
            f"Base document (country_code={document.country_code}) cannot be attached "
            f"to conversation (country_code={conversation.country_code}). "
            "Documents must be from the same country, region, or global."
        )


class UploadedFileRepository(BaseRepository[UploadedFile]):
    def __init__(self, session):
        super().__init__(session, UploadedFile)

    async def register_upload(
        self,
        *,
        document_id: UUID,
        owner_user_id: Optional[UUID],
        storage_uri: str,
        byte_size: int,
        content_hash: str,
        checksum: Optional[str] = None,
        ingestion_metadata: Optional[dict] = None,
    ) -> UploadedFile:
        """
        Create a new upload record unless an owner/hash duplicate already exists.
        """
        if owner_user_id is not None:
            stmt = select(UploadedFile).where(
                UploadedFile.owner_user_id == owner_user_id,
                UploadedFile.content_hash == content_hash,
            )
            result = await self.session.execute(stmt)
            existing_upload = result.scalar_one_or_none()
            if existing_upload:
                return existing_upload

        upload = UploadedFile(
            document_id=document_id,
            owner_user_id=owner_user_id,
            storage_uri=storage_uri,
            byte_size=byte_size,
            content_hash=content_hash,
            checksum=checksum,
            ingestion_metadata=ingestion_metadata,
        )
        self.session.add(upload)
        await self.session.flush()
        await self.session.refresh(upload)
        return upload

    async def list_for_owner(self, owner_user_id: UUID) -> List[UploadedFileRead]:
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.owner_user_id == owner_user_id)
            .order_by(UploadedFile.created_at)
        )
        result = await self.session.execute(stmt)
        uploads = result.scalars().all()
        return [UploadedFileRead.model_validate(upload) for upload in uploads]

    async def list_for_document(self, document_id: UUID) -> List[UploadedFileRead]:
        stmt = (
            select(UploadedFile)
            .where(UploadedFile.document_id == document_id)
            .order_by(UploadedFile.created_at)
        )
        result = await self.session.execute(stmt)
        uploads = result.scalars().all()
        return [UploadedFileRead.model_validate(upload) for upload in uploads]
