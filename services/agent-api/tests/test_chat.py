import pytest
from httpx import AsyncClient
from shared_data_layer.db.models.conversations import Message
from shared_data_layer.repositories.documents import DocumentRepository
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

from agent_api.services.conversations import ConversationService

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
