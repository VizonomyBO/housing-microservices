from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from shared_data_layer.db.ltree import Ltree
from shared_data_layer.db.maintenance import refresh_active_chunks_view
from shared_data_layer.db.models.documents import (
    BaseDocumentByCountry,
    Document,
)
from shared_data_layer.db.models.retrieval import ActiveChunk
from shared_data_layer.repositories.retrieval import PillarAnswerRepository
from shared_data_layer.testing.base import AsyncBaseTestCase
from shared_data_layer.testing.factories.documents import DocumentFactory
from shared_data_layer.testing.factories.knowledge_graph import (
    GraphEdgeFactory,
    GraphEntityFactory,
    GraphEvidenceFactory,
)
from shared_data_layer.testing.factories.workflow import (
    WorkflowGraphFactory,
    WorkflowNodeFactory,
    WorkflowVersionFactory,
)

pytestmark = pytest.mark.end_to_end


@pytest.mark.asyncio
class TestEndToEndIngestion(AsyncBaseTestCase):
    async def test_document_ingestion_to_graph_rollup(self, db_session):
        base_doc = await DocumentFactory.create_async(
            session=db_session,
            access_scope="base",
            owner_user_id=None,
            country_code="USA",
            status="active",
        )
        chunk = base_doc.chunks[0]

        cache_row = await db_session.execute(
            select(BaseDocumentByCountry).where(
                BaseDocumentByCountry.document_id == base_doc.id,
                BaseDocumentByCountry.country_code == "USA",
            )
        )
        cached = cache_row.scalar_one()
        assert cached.status == base_doc.status
        assert cached.content_hash == base_doc.content_hash

        await refresh_active_chunks_view(db_session)
        active_chunks_rows = await db_session.execute(
            select(ActiveChunk).where(ActiveChunk.document_id == base_doc.id)
        )
        active_chunks = active_chunks_rows.scalars().all()
        assert len(active_chunks) == len(base_doc.chunks)

        entity_a = await GraphEntityFactory.create_async(
            session=db_session,
            country_code=chunk.country_code,
            chunk_id=chunk.id,
            chunk_country_code=chunk.country_code,
            document_id=base_doc.id,
        )
        entity_b = await GraphEntityFactory.create_async(
            session=db_session,
            country_code=chunk.country_code,
            chunk_id=None,
            chunk_country_code=None,
            document_id=base_doc.id,
        )

        edge = await GraphEdgeFactory.create_async(
            session=db_session,
            source=entity_a,
            target=entity_b,
            evidence=[],
        )
        await GraphEvidenceFactory.create_async(
            session=db_session,
            edge=edge,
            chunk=chunk,
            chunk_country_code=chunk.country_code,
        )

        rollup = await db_session.execute(
            text(
                """
                SELECT evidence_chunk_ids, evidence_count
                FROM graph_edge_evidence_rollup
                WHERE edge_id = :edge_id
                """
            ),
            {"edge_id": edge.id},
        )
        row = rollup.first()
        assert row is not None
        assert chunk.id in row.evidence_chunk_ids
        assert row.evidence_count == len(row.evidence_chunk_ids)

    async def test_base_document_without_country_rejected(self, db_session):
        doc = Document(
            owner_user_id=None,
            access_scope="base",
            country_code=None,
            canonical_name="missing-country",
            status="active",
            ingestion_stage="chunk",
            content_hash=uuid4().hex,
        )
        db_session.add(doc)

        with pytest.raises(IntegrityError) as excinfo:
            await db_session.flush()

        assert "ck_documents_base_country_required" in str(excinfo.value)

    async def test_pillar_answer_requires_owner_identity(self, db_session):
        user_doc = await DocumentFactory.create_async(
            session=db_session,
            access_scope="user_private",
        )
        repo = PillarAnswerRepository(db_session)

        with pytest.raises(ValueError, match="owner_user_id is required"):
            await repo.create_pillar_answer(
                owner_user_id=None,
                document_id=user_doc.id,
                country_code=user_doc.country_code or "USA",
                pillar_name="finance",
                content_hash="end2end-hash",
                summary_markdown="Summary",
                answer_json={"key": "value"},
                status="draft",
            )

    async def test_workflow_cycle_trigger_blocks_illegal_update(self, db_session):
        graph = await WorkflowGraphFactory.create_async(
            session=db_session, version_count=0
        )
        version = await WorkflowVersionFactory.create_async(
            session=db_session, graph=graph
        )

        root = await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path=Ltree("root"),
        )
        await WorkflowNodeFactory.create_async(
            session=db_session,
            version=version,
            path=Ltree("root.child"),
        )

        with pytest.raises(Exception) as excinfo:
            await db_session.execute(
                text(
                    """
                    UPDATE workflow_nodes
                    SET path = (:new_path)::ltree
                    WHERE id = :node_id
                    """
                ),
                {"new_path": "root.child.root", "node_id": root.id},
            )
        await db_session.rollback()
        assert "descendant path" in str(excinfo.value)
