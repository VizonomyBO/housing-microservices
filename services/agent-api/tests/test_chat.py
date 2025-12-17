import json

import pytest
from httpx import ASGITransport, AsyncClient
from shared_data_layer.db.models.conversations import Message
from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

from agent_api.services.conversations import ConversationService
from agent_api.agent.runner import LangGraphRunner
from agent_api.http.deps import get_runner

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_chat_uses_runner_and_persists_messages(
    client: AsyncClient,
    db_session,
    test_user_id: str,
):
    conversation = await ConversationService(db_session).ensure_conversation(
        owner_user_id=test_user_id,
        country_code="USA",
        title="chat",
        namespace="default",
        tags=[],
        metadata=None,
    )
    document = await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=conversation.owner_user_id,
        status="active",
        ingestion_stage="activate",
    )
    repo = DocumentRepository(db_session)
    await repo.attach_to_conversation(
        conversation_id=conversation.id,
        document_id=document.id,
        attach_source="test",
        role="primary",
        attached_by_user_id=conversation.owner_user_id,
        visibility_override="visible",
    )
    await db_session.commit()

    resp = await client.post(
        "/v1/chat",
        json={
            "thread_id": str(conversation.id),
            "message": {"type": "user", "content": "hi", "attachments": []},
            "constraints": {"country_code": "USA"},
            "response_mode": "blocking",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["done"]["status"] == "COMPLETED"
    assert body["messages"]
    assert body["messages"][0]["role"] == "assistant"

    messages = (
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        )
        .scalars()
        .all()
    )
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles


@pytest.fixture
async def client_real_runner(app):
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    # Override runner to use real LangGraphRunner so attachment checks apply.
    app.dependency_overrides[get_runner] = lambda: LangGraphRunner(settings=app.state.settings)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_chat_requires_attachments(
    client_real_runner: AsyncClient,
    db_session,
    test_user_id: str,
):
    conversation = await ConversationService(db_session).ensure_conversation(
        owner_user_id=test_user_id,
        country_code="USA",
        title="chat-no-docs",
        namespace="default",
        tags=[],
        metadata=None,
    )
    await db_session.commit()

    resp = await client_real_runner.post(
        "/v1/chat",
        json={
            "thread_id": str(conversation.id),
            "message": {"type": "user", "content": "hi", "attachments": []},
            "constraints": {"country_code": "USA"},
            "response_mode": "blocking",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("error", {}).get("code") == "ATTACHMENTS_REQUIRED"


def _parse_sse_events(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    current: dict[str, object] = {}
    for line in lines:
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event: "):
            current["event"] = line.split("event: ", 1)[1]
        if line.startswith("data: "):
            payload = line.split("data: ", 1)[1]
            try:
                current["data"] = json.loads(payload)
            except json.JSONDecodeError:
                current["data_raw"] = payload
    if current:
        events.append(current)
    return events


async def test_chat_streaming_emits_meta_and_done(client: AsyncClient, db_session):
    payload = {
        "message": {"type": "user", "content": "stream please", "attachments": []},
        "constraints": {"country_code": "USA"},
        "response_mode": "stream",
    }
    async with client.stream("POST", "/v1/chat", json=payload) as response:
        assert response.status_code == 200
        lines = [line async for line in response.aiter_lines()]

    events = _parse_sse_events(lines)
    event_types = [e.get("event") for e in events]
    assert "meta" in event_types
    assert "done" in event_types
    done_event = next(e for e in events if e.get("event") == "done")
    done_payload = done_event["data"]["payload"]
    assert done_payload["status"] == "COMPLETED"
    assert done_payload["thread_id"]
