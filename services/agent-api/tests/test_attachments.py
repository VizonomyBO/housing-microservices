from uuid import UUID

import pytest
from httpx import AsyncClient
from shared_data_layer.db.models.documents import ConversationDocument
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

from agent_api.services.conversations import ConversationService

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_attachment_lifecycle(
    client: AsyncClient,
    db_session,
    test_user_id: str,
):
    conversation = await ConversationService(db_session).ensure_conversation(
        owner_user_id=test_user_id,
        country_code="USA",
        title="test convo",
        namespace="default",
        tags=[],
        metadata=None,
    )
    document = await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=UUID(test_user_id),
        status="active",
        ingestion_stage="activate",
    )
    await db_session.commit()

    attach_resp = await client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(document.id), "visibility": "visible"},
    )
    assert attach_resp.status_code == 201, attach_resp.text
    payload = attach_resp.json()
    assert payload["status"] == "ATTACHED"
    assert payload["attachment"]["document_id"] == str(document.id)

    list_resp = await client.get(f"/v1/conversations/{conversation.id}/attachments")
    assert list_resp.status_code == 200
    listed = list_resp.json()["attachments"]
    assert any(item["document_id"] == str(document.id) for item in listed)

    detach_resp = await client.delete(
        f"/v1/conversations/{conversation.id}/attachments/{document.id}"
    )
    assert detach_resp.status_code == 200
    assert detach_resp.json()["status"] == "DETACHED"

    remaining = await db_session.execute(
        select(ConversationDocument).where(
            ConversationDocument.conversation_id == conversation.id,
            ConversationDocument.document_id == document.id,
            ConversationDocument.deleted_at.is_(None),
        )
    )
    assert remaining.scalar_one_or_none() is None


async def test_attach_inactive_document_rejected(
    client: AsyncClient,
    db_session,
    test_user_id: str,
):
    conversation = await ConversationService(db_session).ensure_conversation(
        owner_user_id=test_user_id,
        country_code="USA",
        title="test convo",
        namespace="default",
        tags=[],
        metadata=None,
    )
    document = await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=UUID(test_user_id),
        status="ingesting",
        ingestion_stage="chunk",
    )
    await db_session.commit()

    attach_resp = await client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(document.id), "visibility": "visible"},
    )
    assert attach_resp.status_code == 409
    detail = attach_resp.json()["error"]["details"]
    assert detail["document_id"] == str(document.id)
    assert detail["ingestion_stage"] == "chunk"
