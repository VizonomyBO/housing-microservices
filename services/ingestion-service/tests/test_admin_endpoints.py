import uuid
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from ingestion_service import main as ingestion_main
from ingestion_service.auth import UserContext


class _FakeRepo:
    def __init__(self, uploads):
        self._uploads = uploads

    async def list_uploads(self, **kwargs):
        return self._uploads

    async def get_upload(self, upload_id):
        for upload in self._uploads:
            if upload.id == upload_id:
                return upload
        return None

    async def set_verified(self, *, upload_id, verified, verified_by, verified_at):
        upload = await self.get_upload(upload_id)
        if upload is None:
            return None
        upload.verified = verified
        upload.verified_by = verified_by
        upload.verified_at = verified_at
        return upload

    async def queue_upload(self, *, upload_id):
        upload = await self.get_upload(upload_id)
        if upload is None:
            return None
        upload.reprocess_status = "queued"
        upload.reprocess_error = None
        upload.reprocess_started_at = None
        upload.reprocess_completed_at = None
        return upload


class _FakeDBResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _FakeDBResult(self._rows)

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_admin_list_documents_returns_serialized_uploads(monkeypatch):
    async def fake_require_user(authorization, settings):
        return UserContext(user_id=str(uuid.uuid4()))

    upload = SimpleNamespace(
        id=uuid.uuid4(),
        country_code="NPL",
        filename="file.pdf",
        storage_uri="s3://bucket/key",
        byte_size=123,
        content_hash="hash",
        source="World Bank",
        uploaded_by=uuid.uuid4(),
        verified=False,
        verified_by=None,
        verified_at=None,
        document_id=None,
        reprocess_status="not_started",
        reprocess_error=None,
        reprocess_started_at=None,
        reprocess_completed_at=None,
        metadata_={"source_type": "pdf"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    fake_repo = _FakeRepo([upload])

    monkeypatch.setattr(ingestion_main, "_require_user", fake_require_user)
    monkeypatch.setattr(ingestion_main, "DocumentUploadRepository", lambda db: fake_repo)

    result = await ingestion_main.admin_list_documents(
        db=object(),
        settings=SimpleNamespace(),
        country_code="npl",
        verified=None,
        reprocess_status=None,
        limit=100,
        offset=0,
        authorization="Bearer token",
    )

    assert result["count"] == 1
    assert result["items"][0]["country_code"] == "NPL"
    assert result["items"][0]["filename"] == "file.pdf"
    assert result["items"][0]["ingestion_progress"] is None


@pytest.mark.asyncio
async def test_admin_get_document_not_found(monkeypatch):
    async def fake_require_user(authorization, settings):
        return UserContext(user_id=str(uuid.uuid4()))

    fake_repo = _FakeRepo([])
    monkeypatch.setattr(ingestion_main, "_require_user", fake_require_user)
    monkeypatch.setattr(ingestion_main, "DocumentUploadRepository", lambda db: fake_repo)

    with pytest.raises(HTTPException) as exc:
        await ingestion_main.admin_get_document(
            upload_id=str(uuid.uuid4()),
            db=object(),
            settings=SimpleNamespace(),
            authorization="Bearer token",
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_admin_reprocess_status_aggregates_rows(monkeypatch):
    async def fake_require_user(authorization, settings):
        return UserContext(user_id=str(uuid.uuid4()))

    monkeypatch.setattr(ingestion_main, "_require_user", fake_require_user)
    db = _FakeDB(
        [
            ("NPL", "not_started", 2),
            ("NPL", "done", 1),
            ("KEN", "reprocessing_cache", 3),
        ]
    )

    result = await ingestion_main.admin_reprocess_status(
        db=db,
        settings=SimpleNamespace(),
        authorization="Bearer token",
    )

    assert result["count"] == 2
    assert result["items"][0]["country_code"] == "KEN"
    assert result["items"][1]["country_code"] == "NPL"


@pytest.mark.asyncio
async def test_admin_upload_document_validates_country_code(monkeypatch):
    async def fake_require_user(authorization, settings):
        return UserContext(user_id=str(uuid.uuid4()))

    monkeypatch.setattr(ingestion_main, "_require_user", fake_require_user)
    upload_file = UploadFile(filename="doc.pdf", file=BytesIO(b"abc"))
    settings = SimpleNamespace(
        allowed_source_types=("pdf", "docx"),
        max_file_size_bytes=1000,
    )

    with pytest.raises(HTTPException) as exc:
        await ingestion_main.admin_upload_document(
            db=object(),
            settings=settings,
            country_code="NP",
            source="World Bank",
            metadata=None,
            file=upload_file,
            authorization="Bearer token",
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_approve_document_queues_upload(monkeypatch):
    async def fake_require_user(authorization, settings):
        return UserContext(user_id=str(uuid.uuid4()))

    upload = SimpleNamespace(
        id=uuid.uuid4(),
        country_code="NPL",
        filename="file.pdf",
        storage_uri="s3://bucket/key",
        byte_size=123,
        content_hash="hash",
        source="World Bank",
        uploaded_by=uuid.uuid4(),
        verified=False,
        verified_by=None,
        verified_at=None,
        document_id=None,
        reprocess_status="not_started",
        reprocess_error=None,
        reprocess_started_at=None,
        reprocess_completed_at=None,
        metadata_={"source_type": "pdf"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    fake_repo = _FakeRepo([upload])
    fake_db = _FakeDB([])

    monkeypatch.setattr(ingestion_main, "_require_user", fake_require_user)
    monkeypatch.setattr(ingestion_main, "DocumentUploadRepository", lambda db: fake_repo)

    result = await ingestion_main.admin_approve_document(
        upload_id=str(upload.id),
        db=fake_db,
        settings=SimpleNamespace(),
        authorization="Bearer token",
    )

    assert result["upload"]["verified"] is True
    assert result["upload"]["reprocess_status"] == "queued"
    assert result["upload"]["ingestion_progress"] is None
