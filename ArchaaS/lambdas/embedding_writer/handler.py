"""Embed chunk manifests and persist them to Postgres."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import boto3
import httpx
from common.db import get_async_session
from common.ingestion import IngestionJobManager, update_document_stage
from shared_data_layer.db.models.documents import Document
from shared_data_layer.db.models.retrieval import Chunk, ChunkMetrics

logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3")
VOYAGE_API_URL = os.environ.get("VOYAGE_API_URL", "https://api.voyageai.com/v1/embeddings")
BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))
MAX_TOKEN_COUNT = 800
EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "1024"))

s3 = boto3.client("s3")


@dataclass(slots=True)
class ChunkPayload:
    content: str
    index: int
    token_count: int
    page_number: int | None
    section_title: str | None
    chunk_type: str
    metadata: dict | None
    content_hash: str | None


def handler(event: dict, context: Any) -> dict:
    return asyncio.run(async_handler(event))


async def async_handler(event: dict) -> dict:
    document_id = event.get("document_id")
    if not document_id:
        raise ValueError("document_id is required")

    if not PROCESSED_BUCKET:
        raise RuntimeError("PROCESSED_BUCKET is not configured")

    ingestion_id = event.get("ingestion_id")
    trace_id = event.get("trace_id")
    chunks_key = (
        event.get("chunks_key")
        or event.get("chunk_result", {}).get("chunks_key")
        or f"processed/{document_id}/chunks.jsonl"
    )

    chunk_payloads = _load_chunks(document_id, chunks_key)
    if not chunk_payloads:
        logger.info("No chunks available for document %s", document_id)
        return {
            "statusCode": 200,
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "chunks_processed": 0,
            "embeddings_written": 0,
        }

    embeddings = await _generate_embeddings([chunk.content for chunk in chunk_payloads])

    document_uuid = UUID(str(document_id))

    async with get_async_session() as session:
        document = await session.get(Document, UUID(str(document_id)))
        if document is None:
            raise LookupError(f"Document {document_id} not found")

        job_manager = IngestionJobManager(session)
        job = await job_manager.start_job(document_uuid, "embed", trace_id=trace_id)
        await update_document_stage(session, document_uuid, stage="embed")

        try:
            inserted = await _persist_chunks(session, document, chunk_payloads, embeddings)
            await job_manager.complete_job(job.id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to persist embeddings for %s", document_id)
            await job_manager.fail_job(
                job.id,
                error_code="EMBEDDING_WRITE_FAILED",
                error_message=str(exc),
            )
            raise

    logger.info(
        "Embedding writer stored %d chunks for %s",
        inserted,
        document_id,
        extra={"document_id": document_id, "chunks": inserted},
    )

    return {
        "statusCode": 200,
        "document_id": document_id,
        "ingestion_id": ingestion_id,
        "chunks_processed": len(chunk_payloads),
        "embeddings_written": sum(1 for emb in embeddings if emb is not None),
    }


def _load_chunks(document_id: str, chunks_key: str) -> list[ChunkPayload]:
    logger.info("Reading chunk manifest s3://%s/%s", PROCESSED_BUCKET, chunks_key)
    response = s3.get_object(Bucket=PROCESSED_BUCKET, Key=chunks_key)
    body = response["Body"].read().decode("utf-8")
    payloads: list[ChunkPayload] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        content = data.get("content", "")
        payloads.append(
            ChunkPayload(
                content=content,
                index=int(data.get("chunk_index", len(payloads))),
                token_count=int(data.get("token_count", 0)),
                page_number=_first_value(data.get("page_numbers")),
                section_title=data.get("section_title"),
                chunk_type=str(data.get("chunk_type", "text")),
                metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
                content_hash=data.get("content_hash"),
            )
        )
    logger.info("Loaded %d chunks for %s", len(payloads), document_id)
    return payloads


async def _generate_embeddings(texts: Sequence[str]) -> list[list[float] | None]:
    if not texts:
        return []
    if not VOYAGE_API_KEY:
        logger.warning("VOYAGE_API_KEY not configured. Writing chunks without embeddings.")
        return [None for _ in texts]

    embeddings: list[list[float]] = []
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        for idx in range(0, len(texts), BATCH_SIZE):
            batch = texts[idx : idx + BATCH_SIZE]
            payload = {
                "model": VOYAGE_MODEL,
                "input": batch,
                "input_type": "document",
                "output_dimension": EMBEDDING_DIMENSION,
            }
            resp = await client.post(VOYAGE_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            batch_vectors = [item["embedding"] for item in data.get("data", [])]
            for vector in batch_vectors:
                if len(vector) != EMBEDDING_DIMENSION:
                    raise ValueError(
                        f"Voyage returned {len(vector)}-d embeddings; expected {EMBEDDING_DIMENSION}"
                    )
            embeddings.extend(batch_vectors)
            logger.info(
                "Generated embeddings batch %d/%d",
                (idx // BATCH_SIZE) + 1,
                (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE,
            )

    if len(embeddings) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch (expected {len(texts)}, got {len(embeddings)})"
        )
    return embeddings


async def _persist_chunks(
    session,
    document: Document,
    payloads: Sequence[ChunkPayload],
    embeddings: Sequence[list[float] | None],
) -> int:
    owner_id = document.owner_user_id
    country_code = (document.country_code or "UNK").upper()
    inserted = 0
    for payload, embedding in zip(payloads, embeddings or [], strict=True):
        chunk_id = uuid4()
        token_count = min(payload.token_count or 0, MAX_TOKEN_COUNT) or None
        metadata = payload.metadata or {}
        metadata.setdefault("ingestion", {"mode": "step_functions"})
        chunk = Chunk(
            id=chunk_id,
            document_id=document.id,
            position=payload.index,
            chunk_type=payload.chunk_type,
            page_number=payload.page_number,
            text_content=payload.content,
            section_path=[payload.section_title] if payload.section_title else None,
            token_count=token_count,
            metadata_=metadata,
            embedding=embedding,
            content_hash=payload.content_hash
            or _chunk_hash(document.id, payload.index, payload.content),
            owner_user_id=owner_id,
            country_code=country_code,
        )
        session.add(chunk)
        session.add(
            ChunkMetrics(
                chunk_id=chunk_id,
                chunk_country_code=country_code,
                retrieval_count=0,
            )
        )
        inserted += 1
    return inserted


def _chunk_hash(document_id: UUID, index: int, content: str) -> str:
    payload = f"{document_id}:{index}:{content}".encode("utf-8", errors="ignore")
    return hashlib.sha256(payload).hexdigest()


def _first_value(values: Any) -> int | None:
    if isinstance(values, list) and values:
        try:
            return int(values[0])
        except (TypeError, ValueError):
            return None
    return None
