from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import Document
from shared_data_layer.testing.factories.documents import DocumentFactory

from agent_api.http import create_app
from tests.utils.auth import make_auth_header


@asynccontextmanager
async def _lifespan(app):
    async with app.router.lifespan_context(app):
        yield


TEST_USER_ID = "22222222-2222-2222-2222-222222222222"


def _auth_headers() -> dict[str, str]:
    return make_auth_header(TEST_USER_ID)


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
async def conversation(session_factory) -> Conversation:
    async with session_factory() as session:
        await session.begin()
        conv = Conversation(id=uuid4(), country_code="LBR", status="active")
        session.add(conv)
        await session.commit()
        return conv


@pytest.fixture
async def text_document(session_factory) -> Document:
    async with session_factory() as session:
        await session.begin()
        doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            country_code="LBR",
            language="en",
        )
        await session.commit()
        return doc


@pytest.fixture
async def image_document(session_factory) -> Document:
    async with session_factory() as session:
        await session.begin()
        doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=0,
            country_code="LBR",
            language="en",
            chunks=[{"chunk_type": "image", "image_caption": "chart"}],
        )
        await session.commit()
        return doc


@pytest.fixture
async def base_document(session_factory) -> Document:
    async with session_factory() as session:
        await session.begin()
        doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            access_scope="base",
            owner_user_id=None,
            country_code="LBR",
            metadata_={"auto_attach_enabled": True},
        )
        await session.commit()
        return doc


@pytest.fixture
async def arg_conversation(session_factory) -> Conversation:
    async with session_factory() as session:
        await session.begin()
        conv = Conversation(id=uuid4(), country_code="ARG", status="active")
        session.add(conv)
        await session.commit()
        return conv


@pytest.fixture
async def arg_documents(session_factory) -> tuple[Document, Document]:
    async with session_factory() as session:
        await session.begin()
        user_doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            country_code="ARG",
            language="es",
            owner_user_id=UUID(TEST_USER_ID),
        )
        base_doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            access_scope="base",
            owner_user_id=None,
            country_code="ARG",
            metadata_={"auto_attach_enabled": True},
        )
        await session.commit()
        return user_doc, base_doc


@pytest.fixture
async def pending_document(session_factory) -> Document:
    async with session_factory() as session:
        await session.begin()
        doc = await DocumentFactory.create_async(
            session=session,
            chunk_count=1,
            status="ingesting",
            ingestion_stage="chunk",
        )
        await session.commit()
        return doc


@pytest.mark.asyncio
async def test_attach_document_success(
    api_client: AsyncClient, conversation: Conversation, text_document: Document, session_factory
) -> None:
    resp = await api_client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(text_document.id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201
    listing = await api_client.get(f"/v1/conversations/{conversation.id}/attachments")
    assert listing.status_code == 200
    docs = listing.json()["attachments"]
    assert any(rec["document_id"] == str(text_document.id) for rec in docs)


@pytest.mark.asyncio
async def test_auto_attach_base_docs(
    api_client: AsyncClient,
    conversation: Conversation,
    text_document: Document,
    base_document: Document,
) -> None:
    resp = await api_client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={
            "document_id": str(text_document.id),
            "auto_attach_base_docs": True,
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert str(base_document.id) in body["auto_attached"]


@pytest.mark.asyncio
async def test_rejects_non_text_attachments(
    api_client: AsyncClient, conversation: Conversation, image_document: Document
) -> None:
    resp = await api_client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(image_document.id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 202
    assert resp.headers.get("Retry-After") == "86400"
    body = resp.json()
    assert body["status"] == "FEATURE_DISABLED"


@pytest.mark.asyncio
async def test_rejects_document_until_ingestion_complete(
    api_client: AsyncClient,
    conversation: Conversation,
    pending_document: Document,
) -> None:
    resp = await api_client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(pending_document.id)},
        headers=_auth_headers(),
    )
    assert resp.status_code == 409
    payload = resp.json()
    assert payload["error"]["code"] == "DOCUMENT_NOT_READY"
    assert payload["error"]["details"]["status"] == "ingesting"
    assert payload["error"]["details"]["ingestion_stage"] == "chunk"


@pytest.mark.asyncio
async def test_detach_document(
    api_client: AsyncClient,
    conversation: Conversation,
    text_document: Document,
) -> None:
    await api_client.post(
        f"/v1/conversations/{conversation.id}/attachments",
        json={"document_id": str(text_document.id)},
        headers=_auth_headers(),
    )
    resp = await api_client.delete(
        f"/v1/conversations/{conversation.id}/attachments/{text_document.id}",
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "DETACHED"
    listing = await api_client.get(f"/v1/conversations/{conversation.id}/attachments")
    assert listing.status_code == 200
    docs = listing.json()["attachments"]
    assert all(rec["document_id"] != str(text_document.id) for rec in docs)


@pytest.mark.asyncio
async def test_bulk_attach_by_country(
    api_client: AsyncClient,
    arg_conversation: Conversation,
    arg_documents: tuple[Document, Document],
) -> None:
    user_doc, base_doc = arg_documents
    resp = await api_client.post(
        f"/v1/conversations/{arg_conversation.id}/attachments/bulk",
        json={
            "document_ids": [str(user_doc.id), str(base_doc.id)],
        },
        headers=_auth_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert str(user_doc.id) in body["attached"] or str(base_doc.id) in body["attached"]
    listing = await api_client.get(f"/v1/conversations/{arg_conversation.id}/attachments")
    assert listing.status_code == 200
    attached_ids = {rec["document_id"] for rec in listing.json()["attachments"]}
    assert str(user_doc.id) in attached_ids or str(base_doc.id) in attached_ids
