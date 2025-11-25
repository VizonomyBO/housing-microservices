import pytest
from uuid import UUID

from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.testing.base import AsyncBaseTestCase
from shared_data_layer.testing.factories.users import UserFactory
from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.retrieval import ChunkFactory


@pytest.mark.asyncio
class TestIntegration(AsyncBaseTestCase):
    async def test_document_repository_flow(self, db_session):
        # 1. Create User
        user = await UserFactory.create_async(session=db_session)
        assert isinstance(user.id, UUID)

        # 2. Create Document with Chunks
        document = await DocumentFactory.create_async(session=db_session, owner_user_id=user.id)
        chunk1 = await ChunkFactory.create_async(session=db_session, document=document, chunk_index=0, text="Chunk 1")
        chunk2 = await ChunkFactory.create_async(session=db_session, document=document, chunk_index=1, text="Chunk 2")

        # 3. Use Repository
        # Refresh document to ensure chunks are visible
        await db_session.refresh(document, attribute_names=["chunks"])
        repo = DocumentRepository(db_session)
        doc_read = await repo.get_document_with_chunks(document.id)

        # 4. Verify
        assert doc_read is not None
        assert doc_read.id == document.id
        assert len(doc_read.chunks) == 2
        assert doc_read.chunks[0].text == "Chunk 1"
        assert doc_read.chunks[1].text == "Chunk 2"
