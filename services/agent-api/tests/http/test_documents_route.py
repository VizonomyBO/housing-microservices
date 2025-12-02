from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from agent_api.http import create_app


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


TEST_USER_ID = "33333333-3333-3333-3333-333333333333"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_USER_ID}"}


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
        "content": "# Heading\nSome demo content",
        "country_code": "LBR",
        "language": "en",
        "tags": ["finance"],
    }
    response = await api_client.post("/v1/documents/upload", json=payload, headers=_auth_headers())
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "COMPLETED"
    assert data["document_id"]
    assert data["ingestion_id"]
    assert data["upload"]["status"] == "completed"


async def test_upload_document_dedupes_existing(api_client: AsyncClient) -> None:
    suffix = uuid4().hex
    payload = {
        "document_name": f"FY24 Dedup Report {suffix}",
        "content": "## Intro\nContent",
        "country_code": "LBR",
        "language": "en",
    }
    headers = _auth_headers()
    first = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
    assert first.status_code == 201
    second = await api_client.post("/v1/documents/upload", json=payload, headers=headers)
    assert second.status_code == 200
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
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "FEATURE_DISABLED"
    assert data["document_id"] is None
    assert response.headers["Retry-After"] == "86400"
