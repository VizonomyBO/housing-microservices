from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import HumanMessage
from shared_data_layer.db.session import DatabaseSessionManager

from agent_api.http import create_app
from repositories.agent_checkpoint_repository import AgentCheckpointRepository
from services import AttachmentService, DocumentNotReadyError
from state.agent_state import MessageSnapshot
from tests.utils.auth import make_auth_header


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


TEST_USER_ID = "33333333-3333-3333-3333-333333333333"


def _auth_headers(user_id: str = TEST_USER_ID) -> dict[str, str]:
    return make_auth_header(user_id)


@pytest.fixture
async def api_client(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
    session_factory,
):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.mark.asyncio
async def test_create_and_get_conversation(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    payload = {
        "title": "Reduced Profile Smoke",
        "country_code": "usa",
        "tags": ["Demo", "Reduced_E2E"],
    }
    resp = await api_client.post("/v1/conversations", json=payload, headers=_auth_headers(user_id))
    assert resp.status_code == 201
    body = resp.json()
    conversation = body["conversation"]
    assert conversation["owner_user_id"] == user_id
    assert conversation["country_code"] == "USA"
    assert conversation["tags"] == ["demo", "reduced_e2e"]
    assert body["created"] is True

    conversation_id = conversation["conversation_id"]
    get_resp = await api_client.get(
        f"/v1/conversations/{conversation_id}", headers=_auth_headers(user_id)
    )
    assert get_resp.status_code == 200
    fetched = get_resp.json()["conversation"]
    assert fetched["conversation_id"] == conversation_id
    assert fetched["namespace"] == "reduced-e2e"


@pytest.mark.asyncio
async def test_create_conversation_idempotent(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    resp1 = await api_client.post(
        "/v1/conversations",
        json={"title": "Session"},
        headers=_auth_headers(user_id),
    )
    assert resp1.status_code == 201
    conv1 = resp1.json()["conversation"]

    resp2 = await api_client.post(
        "/v1/conversations",
        json={"title": "Session"},
        headers=_auth_headers(user_id),
    )
    assert resp2.status_code == 200
    conv2 = resp2.json()["conversation"]
    assert conv1["conversation_id"] == conv2["conversation_id"]
    assert resp2.json()["created"] is False


@pytest.mark.asyncio
async def test_conversation_enforces_owner(api_client: AsyncClient) -> None:
    owner_user_id = str(uuid4())
    other_user_id = str(uuid4())
    resp = await api_client.post("/v1/conversations", json={}, headers=_auth_headers(owner_user_id))
    assert resp.status_code == 201
    conversation_id = resp.json()["conversation"]["conversation_id"]

    other_resp = await api_client.get(
        f"/v1/conversations/{conversation_id}",
        headers=_auth_headers(other_user_id),
    )
    assert other_resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_requires_auth(api_client: AsyncClient) -> None:
    resp = await api_client.post("/v1/conversations", json={})
    assert resp.status_code == 401

    resp = await api_client.get("/v1/conversations/some-id")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_conversation_uses_deterministic_namespace(api_client: AsyncClient) -> None:
    namespace = "custom-namespace"
    user_id = str(uuid4())
    resp = await api_client.post(
        "/v1/conversations",
        json={"namespace": namespace},
        headers=_auth_headers(user_id),
    )
    assert resp.status_code == 201
    conv = resp.json()["conversation"]
    expected_id = str(uuid5(NAMESPACE_URL, f"{namespace}-{user_id}"))
    assert conv["conversation_id"] == expected_id


@pytest.mark.asyncio
async def test_list_conversations_returns_paginated_results(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    create_resp = await api_client.post(
        "/v1/conversations",
        json={"title": "Inventory", "tags": ["Inventory"], "country_code": "USA"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    conversation_id = create_resp.json()["conversation"]["conversation_id"]

    upload_payload = {
        "document_name": "Inventory Doc",
        "content": "# Test\nbody",
        "country_code": "USA",
        "language": "en",
        "tags": ["inventory"],
    }
    upload_resp = await api_client.post(
        "/v1/documents/upload",
        json=upload_payload,
        headers=headers,
    )
    assert upload_resp.status_code == 201
    document_id = upload_resp.json()["document_id"]

    attach_resp = await api_client.post(
        f"/v1/conversations/{conversation_id}/attachments",
        json={"document_id": document_id},
        headers=headers,
    )
    assert attach_resp.status_code in (201, 202)

    list_resp = await api_client.get(
        "/v1/conversations",
        params=[("tags", "inventory"), ("page_size", "5")],
        headers=headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    conversations = body["conversations"]
    assert conversations
    target = next(item for item in conversations if item["conversation_id"] == conversation_id)
    assert target["document_count"] >= 1
    assert body["pagination"]["page"] == 1
    assert "request_id" in body


@pytest.mark.asyncio
async def test_conversation_summary_reports_attachment_counts(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    create_resp = await api_client.post(
        "/v1/conversations",
        json={"title": "Summary", "country_code": "USA"},
        headers=headers,
    )
    conversation_id = create_resp.json()["conversation"]["conversation_id"]

    upload_resp = await api_client.post(
        "/v1/documents/upload",
        json={
            "document_name": "Summary Doc",
            "content": "contents",
            "country_code": "USA",
            "language": "en",
        },
        headers=headers,
    )
    doc_id = upload_resp.json()["document_id"]
    await api_client.post(
        f"/v1/conversations/{conversation_id}/attachments",
        json={"document_id": doc_id},
        headers=headers,
    )

    summary_resp = await api_client.get(
        f"/v1/conversations/{conversation_id}/summary",
        headers=headers,
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["attachment_count"] >= 1
    assert summary["message_count"] == 0
    assert summary["user_prompt_count"] == 0


@pytest.mark.asyncio
async def test_get_conversation_supports_pagination(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    create_resp = await api_client.post("/v1/conversations", json={}, headers=headers)
    conversation_id = create_resp.json()["conversation"]["conversation_id"]

    async with DatabaseSessionManager.session() as session:
        repo = AgentCheckpointRepository(session)
        base_time = datetime.now(UTC)
        snapshots = [
            MessageSnapshot(
                message=HumanMessage(content=f"msg-{idx}"),
                stored_at=base_time + timedelta(seconds=idx),
                metadata={"role": "user"},
            )
            for idx in range(25)
        ]
        await repo.append_messages(conversation_id, snapshots)
        await session.commit()

    first = await api_client.get(
        f"/v1/conversations/{conversation_id}",
        params={"limit": 10},
        headers=headers,
    )
    assert first.status_code == 200
    body = first.json()
    assert len(body["messages"]) == 10
    assert body["page_info"]["remaining_count"] == 15
    cursor = body["page_info"]["next_cursor"]
    assert cursor

    second = await api_client.get(
        f"/v1/conversations/{conversation_id}",
        params={"limit": 10, "cursor": cursor},
        headers=headers,
    )
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["messages"][0]["content"] == "msg-10"
    assert second_body["page_info"]["remaining_count"] == 5


@pytest.mark.asyncio
async def test_conversation_list_requires_auth(api_client: AsyncClient) -> None:
    resp = await api_client.get("/v1/conversations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_attachment_rejected_until_document_active(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    conv_resp = await api_client.post(
        "/v1/conversations",
        json={"country_code": "USA"},
        headers=headers,
    )
    conversation_id = conv_resp.json()["conversation"]["conversation_id"]

    upload_resp = await api_client.post(
        "/v1/documents/upload",
        json={
            "document_name": "Pending Upload",
            "content": "temporary content",
            "country_code": "USA",
            "language": "en",
        },
        headers=headers,
    )
    doc_id = upload_resp.json()["document_id"]

    async def _raise_not_ready(*args, **kwargs):
        raise DocumentNotReadyError(UUID(doc_id), "ingesting", "chunk")

    monkeypatch.setattr(AttachmentService, "attach_document", _raise_not_ready)

    attach_resp = await api_client.post(
        f"/v1/conversations/{conversation_id}/attachments",
        json={"document_id": doc_id},
        headers=headers,
    )
    assert attach_resp.status_code == 409
    payload = attach_resp.json()
    assert payload["error"]["code"] == "DOCUMENT_NOT_READY"
