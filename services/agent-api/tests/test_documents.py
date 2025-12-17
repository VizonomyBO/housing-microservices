import json
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from shared_data_layer.db.models.documents import UploadedFile
from shared_data_layer.testing.factories.documents import DocumentFactory
from sqlalchemy import select

pytestmark = pytest.mark.asyncio(loop_scope="session")


class FakeResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.text = json.dumps(data)

    def json(self) -> dict:
        return self._data


class FakeAsyncClient:
    def __init__(self, *args, response_data: dict | None = None, **kwargs):
        self._response_data = response_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict | None = None, headers=None):
        data = self._response_data or {
            "status": "COMPLETED",
            "document_id": str(uuid4()),
            "ingestion_id": str(uuid4()),
            "content_hash": uuid4().hex,
            "upload": {"status": "completed"},
        }
        return FakeResponse(201, data)


async def test_document_upload_proxies_and_tracks_upload(
    client: AsyncClient, db_session, monkeypatch, test_user_id: str
):
    document = await DocumentFactory.create_async(
        session=db_session,
        owner_user_id=UUID(test_user_id),
        status="active",
        ingestion_stage="activate",
    )
    await db_session.commit()

    response_data = {
        "status": "COMPLETED",
        "document_id": str(document.id),
        "ingestion_id": str(uuid4()),
        "content_hash": document.content_hash,
        "upload": {"status": "completed"},
    }
    monkeypatch.setattr(
        "agent_api.http.routes.documents.httpx.AsyncClient",
        lambda *_args, **_kwargs: FakeAsyncClient(response_data=response_data),
    )

    payload = {
        "document_name": "sample.txt",
        "content": "hello world",
        "chunk_type": "text",
        "country_code": "USA",
    }
    resp = await client.post("/v1/documents/upload", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["document_id"]

    uploads = (await db_session.execute(select(UploadedFile))).scalars().all()
    assert uploads, "Expected an upload record to be created"
    upload = uploads[0]
    assert str(upload.document_id) == response_data["document_id"]
    assert upload.content_hash == response_data["content_hash"]
