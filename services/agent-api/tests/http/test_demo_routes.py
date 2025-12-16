from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy.ext.asyncio import create_async_engine

from agent_api.http import create_app
from tests.utils.auth import make_auth_header


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


LONG_TEXT = " ".join(["Demo policy content"] * 80)


def _auth_headers(user_id: str) -> dict[str, str]:
    return make_auth_header(user_id)


@pytest.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch, database_url: str, engine):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("SERVICE_MODE", "reduced")
    monkeypatch.setenv("REDUCED_SCOPE_ENABLED", "1")
    engine = create_async_engine(async_url, pool_size=5, max_overflow=5)
    DatabaseSessionManager.override_engine(engine)
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_reset_conversation_removes_messages_and_attachments(
    api_client: AsyncClient,
) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    conv_resp = await api_client.post(
        "/v1/conversations",
        json={"country_code": "USA", "tags": ["reduced_e2e"]},
        headers=headers,
    )
    conversation_id = conv_resp.json()["conversation"]["conversation_id"]

    doc_payload = {
        "document_name": "Policy Memo",
        "content": LONG_TEXT,
        "country_code": "USA",
        "language": "en",
        "metadata": {"document_alias": "DOC_POLICY"},
    }
    upload_resp = await api_client.post("/v1/documents/upload", json=doc_payload, headers=headers)
    document_id = upload_resp.json()["document_id"]
    attach_payload = {"document_id": document_id}
    attach_resp = await api_client.post(
        f"/v1/conversations/{conversation_id}/attachments",
        json=attach_payload,
        headers=headers,
    )
    assert attach_resp.status_code in (201, 202)

    reset_resp = await api_client.post("/v1/demo/reset-conversation", json={}, headers=headers)
    assert reset_resp.status_code == 200
    body = reset_resp.json()
    assert body["detached_documents"] >= 1

    attachments_after = await api_client.get(
        f"/v1/conversations/{conversation_id}/attachments",
        headers=headers,
    )
    assert attachments_after.status_code == 200
    assert attachments_after.json()["attachments"] == []


@pytest.mark.asyncio
async def test_reset_conversation_blocks_other_user(api_client: AsyncClient) -> None:
    owner_id = str(uuid4())
    headers = _auth_headers(owner_id)
    conv_resp = await api_client.post("/v1/conversations", json={}, headers=headers)
    conversation_id = conv_resp.json()["conversation"]["conversation_id"]

    other_resp = await api_client.post(
        "/v1/demo/reset-conversation",
        json={"conversation_id": conversation_id},
        headers=_auth_headers(str(uuid4())),
    )
    assert other_resp.status_code == 404


@pytest.mark.asyncio
async def test_purge_documents_by_alias(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    aliases = ["DOC_POLICY", "DOC_LEDGER"]
    doc_ids: list[str] = []
    for alias in aliases:
        payload = {
            "document_name": alias,
            "content": f"{alias} {LONG_TEXT}",
            "country_code": "USA",
            "language": "en",
            "metadata": {"document_alias": alias},
        }
        resp = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
        doc_ids.append(resp.json()["document_id"])

    purge_resp = await api_client.post(
        "/v1/demo/purge-documents",
        json={"document_aliases": [aliases[0]]},
        headers=headers,
    )
    assert purge_resp.status_code == 200
    result = purge_resp.json()
    assert result["purged_documents"] == 1
    assert doc_ids[0] in result["document_ids"]

    reupload_payload = {
        "document_name": aliases[0],
        "content": f"{aliases[0]} {LONG_TEXT}",
        "country_code": "USA",
        "language": "en",
        "metadata": {"document_alias": aliases[0]},
    }
    reupload_resp = await api_client.post(
        "/v1/documents/upload",
        json=reupload_payload,
        headers=headers,
    )
    assert reupload_resp.status_code == 201
    assert reupload_resp.json()["status"] == "COMPLETED"

    dedupe_resp = await api_client.post(
        "/v1/documents/upload",
        json={
            "document_name": aliases[1],
            "content": f"{aliases[1]} {LONG_TEXT}",
            "country_code": "USA",
            "language": "en",
            "metadata": {"document_alias": aliases[1]},
        },
        headers=headers,
    )
    assert dedupe_resp.status_code in (200, 201)
    assert dedupe_resp.json()["status"] == "DEDUPED"


@pytest.mark.asyncio
async def test_demo_endpoints_require_auth(api_client: AsyncClient) -> None:
    resp = await api_client.post("/v1/demo/reset-conversation", json={})
    assert resp.status_code == 401

    resp = await api_client.post("/v1/demo/purge-documents", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_demo_endpoints_disabled_outside_reduced(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("SERVICE_MODE", "standard")
    monkeypatch.setenv("REDUCED_SCOPE_ENABLED", "0")
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/v1/demo/reset-conversation",
                json={},
                headers=_auth_headers(str(uuid4())),
            )
            assert resp.status_code == 404
