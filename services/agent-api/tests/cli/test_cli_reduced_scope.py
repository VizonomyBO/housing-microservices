from __future__ import annotations

import asyncio

import pytest
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import Document, IngestionJob
from shared_data_layer.db.models.retrieval import PillarAnswer
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import delete, select
from typer.testing import CliRunner

from agent_api.cli import app
from repositories.conversation_scope_repository import ConversationScopeRepository

pytestmark = pytest.mark.asyncio(loop_scope="session")


runner = CliRunner()


async def test_cli_run_ingestion(
    monkeypatch: pytest.MonkeyPatch, database_url: str, db_session
) -> None:
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    document = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    document.status = "ingesting"
    document.ingestion_stage = "chunk"
    document.ingestion_started_at = None
    document.ingestion_completed_at = None
    document_id = document.id
    await db_session.commit()
    result = await asyncio.to_thread(runner.invoke, app, ["run-ingestion", str(document_id)])
    await db_session.begin()
    assert result.exit_code == 0, result.stdout
    jobs = (
        (
            await db_session.execute(
                select(IngestionJob).where(IngestionJob.document_id == document_id)
            )
        )
        .scalars()
        .all()
    )
    refreshed = await db_session.get(Document, document_id)
    await db_session.refresh(refreshed)
    assert jobs
    assert refreshed is not None
    assert refreshed.ingestion_stage == "activate"
    await db_session.execute(delete(Document).where(Document.id == document_id))
    await db_session.commit()
    await db_session.begin()


async def test_cli_generate_pillars(
    monkeypatch: pytest.MonkeyPatch, database_url: str, db_session
) -> None:
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    document = await DocumentFactory.create_async(session=db_session, chunk_count=1)
    conversation = Conversation(
        owner_user_id=document.owner_user_id,
        country_code=document.country_code,
        status="active",
    )
    db_session.add(conversation)
    await db_session.flush()
    conversation_id = str(conversation.id)
    scope_repo = ConversationScopeRepository(db_session)
    await scope_repo.ensure_attachment(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="cli",
    )
    await db_session.commit()
    result = await asyncio.to_thread(
        runner.invoke,
        app,
        [
            "generate-pillars",
            "--conversation-id",
            conversation_id,
            "--pillar",
            "revenues",
        ],
    )
    await db_session.begin()
    assert result.exit_code == 0, result.stdout
    answers = (await db_session.execute(select(PillarAnswer))).scalars().all()
    assert answers
    await db_session.execute(delete(Conversation).where(Conversation.id == conversation.id))
    await db_session.execute(delete(Document).where(Document.id == document.id))
    await db_session.commit()
    await db_session.begin()


pytestmark = pytest.mark.asyncio(loop_scope="session")
