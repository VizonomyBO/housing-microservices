from __future__ import annotations

from uuid import uuid4

import pytest
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import Artifact, Document
from shared_data_layer.db.models.retrieval import PillarAnswer, PillarAnswerSource
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

from repositories.conversation_scope_repository import ConversationScopeRepository
from services import PillarService, ReducedScopeIngestionJobService
from services.reduced_scope_runtime import (
    IngestionCompletionPayload,
    ReducedScopeWorkerRuntime,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _runtime(session) -> ReducedScopeWorkerRuntime:
    ingestion = ReducedScopeIngestionJobService(session)
    pillar_service = PillarService(session)
    return ReducedScopeWorkerRuntime(
        session=session,
        ingestion_service=ingestion,
        pillar_service=pillar_service,
        allowed_chunk_types=("text",),
    )


async def test_complete_ingestion_job_updates_document(db_session) -> None:
    document = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    document.status = "ingesting"
    document.ingestion_stage = "chunk"
    document.ingestion_started_at = None
    document.ingestion_completed_at = None
    runtime = await _runtime(db_session)
    summary = await runtime.complete_ingestion_job(
        document.id,
        payload=IngestionCompletionPayload(metadata={"source": "test"}),
    )
    await db_session.flush()

    refreshed = await db_session.get(Document, document.id)
    assert refreshed is not None
    assert refreshed.ingestion_stage == "activate"
    assert summary.document_id == document.id


async def test_generate_pillar_answers_creates_sources(db_session) -> None:
    document = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    conversation = Conversation(
        id=uuid4(),
        owner_user_id=document.owner_user_id,
        country_code=document.country_code,
        status="active",
    )
    db_session.add(conversation)
    await db_session.flush()
    scope_repo = ConversationScopeRepository(db_session)
    await scope_repo.ensure_attachment(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="test",
    )
    runtime = await _runtime(db_session)
    answers = await runtime.generate_pillar_answers(
        conversation_id=str(conversation.id),
        pillars=["revenues"],
    )
    await db_session.flush()

    assert answers
    stored_answer = await db_session.scalar(
        select(PillarAnswer).where(PillarAnswer.id == answers[0].id)
    )
    assert stored_answer is not None
    sources = (
        (
            await db_session.execute(
                select(PillarAnswerSource).where(
                    PillarAnswerSource.pillar_answer_id == stored_answer.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert sources


async def test_generate_artifact_creates_placeholder(db_session) -> None:
    document = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    conversation = Conversation(
        id=uuid4(),
        owner_user_id=document.owner_user_id,
        country_code=document.country_code,
        status="active",
    )
    db_session.add(conversation)
    await db_session.flush()
    scope_repo = ConversationScopeRepository(db_session)
    await scope_repo.ensure_attachment(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="test",
    )
    runtime = await _runtime(db_session)
    artifacts = await runtime.generate_artifact(
        conversation_id=conversation.id,
        artifact_type="chat_export",
    )
    await db_session.flush()

    assert artifacts
    saved = await db_session.scalar(
        select(Artifact)
        .where(Artifact.document_id == document.id)
        .where(Artifact.artifact_type == "chat_export")
    )
    assert saved is not None
    assert saved.metadata_
