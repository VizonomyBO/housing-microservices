from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import ConversationDocument
from shared_data_layer.db.models.retrieval import Chunk, PillarAnswer, PillarAnswerSource
from shared_data_layer.testing.factories.documents import DocumentFactory

from agent_api.http import create_app

pytestmark = pytest.mark.asyncio(loop_scope="session")


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


@pytest.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch, database_url: str):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
async def pillar_dataset(session_factory):
    async with session_factory() as session:
        await session.begin()
        document = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            country_code="LBR",
            language="en",
        )
        chunk = document.chunks[0]
        answer = PillarAnswer(
            owner_user_id=document.owner_user_id,
            document_id=document.id,
            country_code=document.country_code or "LBR",
            pillar_name="revenues",
            content_hash=document.content_hash,
            summary_markdown="Summary",
            answer_json={"value": 0.8},
            status="published",
            generated_at=datetime.now(UTC),
        )
        session.add(answer)
        await session.flush()

        text_source = PillarAnswerSource(
            pillar_answer_id=answer.id,
            chunk_id=chunk.id,
            chunk_country_code=chunk.country_code,
            contribution_type="text",
            weight=1.0,
            evidence_text=chunk.text_content or "Segment",
            page_number=1,
        )
        session.add(text_source)

        image_chunk = Chunk(
            document_id=document.id,
            position=999,
            chunk_type="image",
            content_hash=document.content_hash,
            owner_user_id=document.owner_user_id,
            country_code=document.country_code or "LBR",
            image_caption="diagram",
        )
        session.add(image_chunk)
        await session.flush()

        image_source = PillarAnswerSource(
            pillar_answer_id=answer.id,
            chunk_id=image_chunk.id,
            chunk_country_code=image_chunk.country_code,
            contribution_type="image",
            weight=1.0,
            evidence_text="Image evidence",
        )
        session.add(image_source)

        conversation = Conversation(id=uuid4(), country_code=document.country_code, status="active")
        session.add(conversation)
        await session.flush()
        convo_doc = ConversationDocument(
            conversation_id=conversation.id,
            document_id=document.id,
            attach_source="user_request",
            role="primary",
        )
        session.add(convo_doc)
        await session.commit()
        return {
            "answer": answer,
            "conversation": conversation,
        }


async def test_country_pillars_filter_to_text_sources(
    api_client: AsyncClient, pillar_dataset
) -> None:
    response = await api_client.get("/v1/pillars/LBR")
    assert response.status_code == 200
    body = response.json()
    assert body["pillars"]
    sources = body["pillars"][0]["sources"]
    assert len(sources) == 1
    assert sources[0]["chunk_type"] == "text"


async def test_conversation_pillars_respects_scope(api_client: AsyncClient, pillar_dataset) -> None:
    conversation = pillar_dataset["conversation"]
    response = await api_client.get(f"/v1/conversations/{conversation.id}/pillars")
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == str(conversation.id)
    assert len(data["pillars"]) == 1


async def test_country_pillars_generate_answers_inline(
    api_client: AsyncClient, session_factory
) -> None:
    async with session_factory() as db_session:
        await db_session.begin()
        try:
            await DocumentFactory.create_async(
                session=db_session,
                chunk_count=1,
                access_scope="base",
                owner_user_id=None,
                country_code="LBR",
            )
            await db_session.commit()
        finally:
            await db_session.rollback()
    response = await api_client.get("/v1/pillars/LBR")
    assert response.status_code == 200
    data = response.json()
    assert data["pillars"], data
