from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from shared_data_layer.db.models.documents import Document
from shared_data_layer.repositories.base import BaseRepository
from shared_data_layer.schemas.documents import DocumentRead, DocumentWithChunksRead


class DocumentRepository(BaseRepository[Document]):
    def __init__(self, session):
        super().__init__(session, Document)

    async def get_document_with_chunks(self, document_id: UUID) -> Optional[DocumentWithChunksRead]:
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.chunks)) # Assuming 'chunks' relationship exists on Document
        )
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if document:
            return DocumentWithChunksRead.model_validate(document)
        return None

    async def list_documents_for_country(self, country_code: str, include_base: bool = True) -> List[DocumentRead]:
        stmt = select(Document).where(Document.country_code == country_code)
        # Logic for include_base could be added here if 'base' means something specific in access_scope or similar
        result = await self.session.execute(stmt)
        documents = result.scalars().all()
        return [DocumentRead.model_validate(doc) for doc in documents]
