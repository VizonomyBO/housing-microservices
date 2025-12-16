from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_api.http import create_app
from tests.utils.auth import make_auth_header


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


TEST_USER_ID = "33333333-3333-3333-3333-333333333333"
LONG_TEXT = " ".join(["Housing policy detail"] * 80)


def _auth_headers(user_id: str = TEST_USER_ID) -> dict[str, str]:
    return make_auth_header(user_id)


@pytest.fixture
async def api_client(monkeypatch: pytest.MonkeyPatch, database_url: str, engine):
    async_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    monkeypatch.setenv("DATABASE_URL", async_url)
    app = create_app()
    async with _lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_upload_document_creates_rows(api_client: AsyncClient) -> None:
    suffix = uuid4().hex
    payload = {
        "document_name": f"FY24 Fiscal Report {suffix}",
        "content": LONG_TEXT,
        "country_code": "LBR",
        "language": "en",
        "tags": ["finance"],
    }
    response = await api_client.post("/v1/documents/upload", json=payload, headers=_auth_headers())
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["document_id"]
    assert data["ingestion_id"]
    assert data["upload"]["status"] == "completed"


async def test_upload_document_dedupes_existing(api_client: AsyncClient) -> None:
    suffix = uuid4().hex
    payload = {
        "document_name": f"FY24 Dedup Report {suffix}",
        "content": LONG_TEXT,
        "country_code": "LBR",
        "language": "en",
    }
    headers = _auth_headers()
    first = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    second = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["status"] == "DEDUPED"
    assert body["ingestion_id"] is None


async def test_upload_document_rejects_image_chunks(api_client: AsyncClient) -> None:
    suffix = uuid4().hex
    payload = {
        "document_name": f"Vision Attachment {suffix}",
        "content": "![img](s3://asset)",
        "chunk_type": "image",
        "country_code": "LBR",
        "language": "en",
    }
    response = await api_client.post("/v1/documents/upload", json=payload, headers=_auth_headers())
    assert response.status_code == 202, response.text
    data = response.json()
    assert data["status"] == "FEATURE_DISABLED"
    assert data["document_id"] is None
    assert response.headers["Retry-After"] == "86400"


async def test_list_documents_filters_by_hash(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    payload = {
        "document_name": "Ledger Snapshot",
        "content": LONG_TEXT,
        "country_code": "USA",
        "language": "en",
        "tags": ["reduced_e2e"],
    }
    upload_resp = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
    assert upload_resp.status_code == 201, upload_resp.text
    content_hash = upload_resp.json()["content_hash"]

    list_resp = await api_client.get(
        "/v1/documents",
        params=[("content_hash", content_hash), ("tags", "reduced_e2e")],
        headers=headers,
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["documents"]
    document = body["documents"][0]
    assert document["content_hash"] == content_hash
    assert document["canonical_name"] == "Ledger Snapshot"


async def test_list_documents_requires_auth(api_client: AsyncClient) -> None:
    resp = await api_client.get("/v1/documents")
    assert resp.status_code == 401


async def test_list_documents_filters_by_country(api_client: AsyncClient) -> None:
    user_id = str(uuid4())
    headers = _auth_headers(user_id)
    usa_payload = {
        "document_name": "USA Memo",
        "content": LONG_TEXT,
        "country_code": "USA",
    }
    arg_payload = {
        "document_name": "ARG Memo",
        "content": LONG_TEXT,
        "country_code": "ARG",
    }
    resp_usa = await api_client.post("/v1/documents/upload", json=usa_payload, headers=headers)
    resp_arg = await api_client.post("/v1/documents/upload", json=arg_payload, headers=headers)
    assert resp_usa.status_code == 201, resp_usa.text
    assert resp_arg.status_code == 201, resp_arg.text

    filtered = await api_client.get(
        "/v1/documents", params=[("country_code", "ARG")], headers=headers
    )
    assert filtered.status_code == 200
    docs = filtered.json()["documents"]
    assert all(doc["country_code"] == "ARG" for doc in docs)
    assert any(doc["canonical_name"] == "ARG Memo" for doc in docs)
