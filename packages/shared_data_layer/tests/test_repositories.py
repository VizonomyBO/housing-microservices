import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.ltree import Ltree
from shared_data_layer.repositories.documents import (
    DocumentRepository,
    UploadedFileRepository,
)
from shared_data_layer.repositories.knowledge_graph import KnowledgeGraphRepository
from shared_data_layer.repositories.workflow import WorkflowGraphRepository
from shared_data_layer.testing.factories.documents import (
    ChunkFactory,
    DocumentFactory,
)
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
    GraphEntityFactory,
)
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
    WorkflowVersionFactory,
)


@pytest.mark.asyncio
class TestRepositories:
    async def test_document_repository(self, db_session: AsyncSession):
        repo = DocumentRepository(db_session)

        # Create a document with chunks
        doc = await DocumentFactory.create_async(
            session=db_session, country_code="USA", chunks=[]
        )
        chunk1 = await ChunkFactory.create_async(session=db_session, document=doc)
        chunk2 = await ChunkFactory.create_async(session=db_session, document=doc)

        doc_id = doc.id
        chunk1_id = chunk1.id
        chunk2_id = chunk2.id

        # Expire session to ensure fresh load of relationships
        await db_session.run_sync(lambda session: session.expire_all())

        # Test get_document_with_chunks
        result = await repo.get_document_with_chunks(doc_id)
        assert result is not None
        assert result.id == doc_id
        assert len(result.chunks) == 2
        assert result.chunks[0].id in [chunk1_id, chunk2_id]

        # Test list_documents_for_country
        doc_uk = await DocumentFactory.create_async(
            session=db_session, country_code="GBR", chunks=[]
        )
        doc_uk_id = doc_uk.id

        us_docs = await repo.list_documents_for_country("USA")
        assert len(us_docs) >= 1
        assert any(d.id == doc_id for d in us_docs)
        assert not any(d.id == doc_uk_id for d in us_docs)
        return

    async def test_uploaded_file_repository(self, db_session: AsyncSession):
        doc = await DocumentFactory.create_async(
            session=db_session, chunk_count=0, country_code="USA"
        )
        repo = UploadedFileRepository(db_session)
        upload = await repo.register_upload(
            document_id=doc.id,
            owner_user_id=doc.owner_user_id,
            storage_uri="s3://bucket/raw.pdf",
            byte_size=1024,
            content_hash="hash-123",
            checksum="checksum",
            ingestion_metadata={"stage": "preflight"},
        )

        duplicate = await repo.register_upload(
            document_id=doc.id,
            owner_user_id=doc.owner_user_id,
            storage_uri="s3://bucket/raw.pdf",
            byte_size=1024,
            content_hash="hash-123",
            checksum="checksum",
        )

        assert upload.id == duplicate.id

        owner_uploads = await repo.list_for_owner(doc.owner_user_id)
        assert len(owner_uploads) == 1
        assert owner_uploads[0].id == upload.id
        assert owner_uploads[0].storage_uri == "s3://bucket/raw.pdf"

        document_uploads = await repo.list_for_document(doc.id)
        assert len(document_uploads) == 1
        assert document_uploads[0].id == upload.id

    async def test_knowledge_graph_repository(self, db_session: AsyncSession):
        repo = KnowledgeGraphRepository(db_session)

        # Create entities and edges
        # Entity A -> Entity B
        entity_a = await GraphEntityFactory.create_async(
            session=db_session, name="Entity A", country_code="USA"
        )
        entity_b = await GraphEntityFactory.create_async(
            session=db_session, name="Entity B", country_code="USA"
        )

        edge = await GraphEdgeFactory.create_async(
            session=db_session,
            source=entity_a,
            target=entity_b,
            edge_type="related_to",
        )

        entity_a_id = entity_a.id
        entity_b_id = entity_b.id
        edge_id = edge.id

        # Expire session to ensure fresh load of relationships
        await db_session.run_sync(lambda session: session.expire_all())

        # Test fetch_entity_with_neighbors
        # We need to refresh/load relationships if factory didn't do it fully
        # for the repo query to work?
        # The repo uses selectinload, so it should fetch fresh.

        result_a = await repo.fetch_entity_with_neighbors(entity_a_id)
        assert result_a is not None
        assert result_a.id == entity_a_id
        # Check outgoing edges
        assert len(result_a.edges_out) == 1
        assert result_a.edges_out[0].target_entity_id == entity_b_id

        # Test list_edges_for_scope
        edges_us = await repo.list_edges_for_scope("USA")
        assert len(edges_us) >= 1
        assert any(e.id == edge_id for e in edges_us)

        # Test scope filtering
        entity_c = await GraphEntityFactory.create_async(
            session=db_session, country_code="GBR"
        )
        entity_d = await GraphEntityFactory.create_async(
            session=db_session, country_code="GBR"
        )
        edge_uk = await GraphEdgeFactory.create_async(
            session=db_session, source=entity_c, target=entity_d, edge_type="related_to"
        )
        edge_uk_id = edge_uk.id

        edges_us_filtered = await repo.list_edges_for_scope("USA")
        assert not any(e.id == edge_uk_id for e in edges_us_filtered)

    async def test_knowledge_graph_materializations_refresh(
        self, db_session: AsyncSession
    ) -> None:
        repo = KnowledgeGraphRepository(db_session)
        # Should not raise even on empty graph
        await repo.refresh_materializations()

    async def test_workflow_repository(self, db_session: AsyncSession):
        repo = WorkflowGraphRepository(db_session)

        # Create a graph with a published version
        graph = await WorkflowGraphFactory.create_async(
            session=db_session,
            domain="policy",
            country_code="USA",
            status="published",
            version_count=0,
        )

        version = await WorkflowVersionFactory.create_async(
            session=db_session,
            graph=graph,
            nodes=[],
            edges=[],
        )

        # Add nodes to published version
        node = await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path=Ltree("A"),
        )

        graph_id = graph.id

        # Expire session to ensure fresh load of relationships
        await db_session.run_sync(lambda session: session.expire_all())

        # Test get_published_workflow
        result = await repo.get_published_workflow(domain="policy", country_code="USA")
        assert result is not None
        assert result.id == graph_id

        assert len(result.versions) >= 1
        # Check if we can find the published version
        assert len(result.versions) >= 1
        assert result.versions[0].nodes
        node_ids = {n.id for n in result.versions[0].nodes}
        assert node.id in node_ids
