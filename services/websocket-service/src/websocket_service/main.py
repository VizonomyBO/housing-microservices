from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

import jwt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from shared_data_layer.db.models import ChatResponseCache
from shared_data_layer.db.models.documents import DocumentUpload
from shared_data_layer.db.session import DatabaseSessionManager
from sqlalchemy import func, select

from websocket_service.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    DatabaseSessionManager.init(settings.database_url)
    app.state.settings = settings
    try:
        yield
    finally:
        await DatabaseSessionManager.dispose()


app = FastAPI(title="WebSocket Service", version="0.1.0", lifespan=lifespan)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _resolve_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization")
    if auth_header is not None and auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return websocket.query_params.get("token")


def _validate_token(token: str | None, settings: Settings) -> None:
    secret = settings.token_secret
    if secret is None:
        return
    if token is None:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        jwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def _extract_ingestion_progress(metadata: Any) -> dict[str, int] | None:
    if not isinstance(metadata, dict):
        return None
    raw_progress = metadata.get("ingestion_progress")
    if not isinstance(raw_progress, dict):
        return None
    keys = (
        "total_chunks",
        "total_batches",
        "processed_chunks",
        "processed_batches",
        "batch_size",
    )
    progress: dict[str, int] = {}
    for key in keys:
        value = raw_progress.get(key)
        if value is None:
            return None
        try:
            progress[key] = int(value)
        except (TypeError, ValueError):
            return None
    return progress


async def _build_country_payload(country_code: str) -> dict[str, Any]:
    async with DatabaseSessionManager.session() as session:
        upload_stmt = select(
            DocumentUpload.reprocess_status,
            func.count(DocumentUpload.id),
        ).where(
            DocumentUpload.country_code == country_code,
            DocumentUpload.verified.is_(True),
        )
        upload_stmt = upload_stmt.group_by(DocumentUpload.reprocess_status)
        upload_rows = (await session.execute(upload_stmt)).all()
        ingesting_stmt = (
            select(DocumentUpload.metadata_)
            .where(
                DocumentUpload.country_code == country_code,
                DocumentUpload.verified.is_(True),
                DocumentUpload.reprocess_status == "ingesting",
            )
            .order_by(DocumentUpload.reprocess_started_at.desc(), DocumentUpload.created_at.desc())
            .limit(1)
        )
        ingesting_row = (await session.execute(ingesting_stmt)).first()

        question_stmt = select(
            ChatResponseCache.status,
            func.count(ChatResponseCache.id),
        ).where(ChatResponseCache.country_code == country_code)
        question_stmt = question_stmt.group_by(ChatResponseCache.status)
        question_rows = (await session.execute(question_stmt)).all()

    upload_counts: dict[str, int] = {}
    for status, count in upload_rows:
        upload_counts[status] = int(count)
    ingesting_progress = _extract_ingestion_progress(ingesting_row[0] if ingesting_row else None)

    question_counts = {"ready": 0, "stale": 0, "reprocessing": 0}
    total_questions = 0
    for status, count in question_rows:
        normalized = str(status)
        if normalized in question_counts:
            question_counts[normalized] = int(count)
        total_questions += int(count)

    overall_status = "idle"
    for candidate in (
        "reprocessing_cache",
        "reprocessing_pdf",
        "ingesting",
        "queued",
        "failed",
        "not_started",
        "done",
    ):
        if upload_counts.get(candidate):
            overall_status = candidate
            break

    return {
        "type": "reprocess_update",
        "country_code": country_code,
        "overall_status": overall_status,
        "upload_counts": upload_counts,
        "ingesting_progress": ingesting_progress,
        "questions": {
            "total": total_questions,
            "ready": question_counts["ready"],
            "stale": question_counts["stale"],
            "reprocessing": question_counts["reprocessing"],
        },
        "pdf_status": "done" if overall_status == "done" else "pending",
    }


async def _build_all_payload() -> dict[str, Any]:
    async with DatabaseSessionManager.session() as session:
        countries_stmt = select(DocumentUpload.country_code).where(
            DocumentUpload.verified.is_(True)
        )
        countries_stmt = countries_stmt.distinct()
        country_rows = (await session.execute(countries_stmt)).all()

    countries = sorted([str(row[0]) for row in country_rows if row[0] is not None])
    items = []
    for country_code in countries:
        items.append(await _build_country_payload(country_code))
    return {"type": "reprocess_update_all", "items": items, "count": len(items)}


async def _stream_country(websocket: WebSocket, country_code: str, settings: Settings) -> None:
    last_payload: str | None = None
    while True:
        payload = await _build_country_payload(country_code)
        encoded = json.dumps(payload, sort_keys=True)
        if encoded != last_payload:
            await websocket.send_json(payload)
            last_payload = encoded
        await asyncio.sleep(settings.websocket_poll_interval_seconds)


async def _stream_all(websocket: WebSocket, settings: Settings) -> None:
    last_payload: str | None = None
    while True:
        payload = await _build_all_payload()
        encoded = json.dumps(payload, sort_keys=True)
        if encoded != last_payload:
            await websocket.send_json(payload)
            last_payload = encoded
        await asyncio.sleep(settings.websocket_poll_interval_seconds)


@app.websocket("/ws/reprocess/{country_code}")
async def ws_reprocess_country(websocket: WebSocket, country_code: str) -> None:
    settings = websocket.app.state.settings
    token = _resolve_token(websocket)
    try:
        _validate_token(token, settings)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    normalized_country = country_code.upper().strip()
    if len(normalized_country) != 3:
        await websocket.close(code=1003)
        return
    try:
        await _stream_country(websocket, normalized_country, settings)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/reprocess/all")
async def ws_reprocess_all(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    token = _resolve_token(websocket)
    try:
        _validate_token(token, settings)
    except HTTPException:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        await _stream_all(websocket, settings)
    except WebSocketDisconnect:
        return

