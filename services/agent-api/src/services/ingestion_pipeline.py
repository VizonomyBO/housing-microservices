"""Real-tooling ingestion pipeline that chunks + embeds uploads."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.documents import Document, IngestionJob
from shared_data_layer.db.models.retrieval import Chunk, ChunkMetrics
from sqlalchemy.ext.asyncio import AsyncSession

from services.document_upload_service import DocumentUploadData
from services.ingestion_job_service import IngestionJobSummary
from services.model_clients import VoyageEmbeddingClientProtocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChunkPayload:
    """Structured chunk emitted by the markdown chunker."""

    content: str
    chunk_index: int
    token_count: int
    page_number: int | None
    section_title: str | None
    content_hash: str


class MarkdownChunker:
    """Best-effort markdown chunker mirroring embedding_writer lambda."""

    TARGET_TOKENS = 500
    MAX_TOKENS = 1000
    MIN_TOKENS = 50
    OVERLAP_TOKENS = 50
    CHARS_PER_TOKEN = 4

    PAGE_PATTERN = re.compile(r"^##?\\s+Page\\s+(?P<page>\\d+)", re.IGNORECASE)
    HEADER_PATTERN = re.compile(r"^#{1,3}\\s+(?P<header>.+)")

    def chunk(self, document_id: str, content: str) -> list[ChunkPayload]:
        if not content.strip():
            return []
        segments = re.split(r"(\\n##?\\s+Page\\s+\\d+|\\n#{1,3}\\s+[^\\n]+)", content)
        current_text = ""
        current_page = 1
        current_header: str | None = None
        chunk_index = 0
        chunks: list[ChunkPayload] = []

        for segment in segments:
            if not segment:
                continue
            page_match = self.PAGE_PATTERN.match(segment.strip())
            if page_match:
                current_page = int(page_match.group("page"))
                continue
            header_match = self.HEADER_PATTERN.match(segment.strip())
            if header_match:
                current_header = header_match.group("header").strip()
            current_text += segment
            if self._token_estimate(current_text) >= self.TARGET_TOKENS:
                chunks.append(
                    self._build_chunk(
                        document_id,
                        chunk_index,
                        current_text,
                        current_page,
                        current_header,
                    )
                )
                chunk_index += 1
                overlap_chars = self.OVERLAP_TOKENS * self.CHARS_PER_TOKEN
                current_text = current_text[-overlap_chars:]

        if current_text.strip() and self._token_estimate(current_text) >= self.MIN_TOKENS:
            chunks.append(
                self._build_chunk(
                    document_id,
                    chunk_index,
                    current_text,
                    current_page,
                    current_header,
                )
            )
        return chunks

    def _token_estimate(self, text: str) -> int:
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def _build_chunk(
        self,
        document_id: str,
        chunk_index: int,
        text: str,
        page_number: int | None,
        header: str | None,
    ) -> ChunkPayload:
        normalized = text.strip()
        token_count = min(self._token_estimate(normalized), self.MAX_TOKENS)
        content_hash = hashlib.sha256(
            f"{document_id}:{chunk_index}:{normalized}".encode()
        ).hexdigest()
        return ChunkPayload(
            content=normalized,
            chunk_index=chunk_index,
            token_count=token_count,
            page_number=page_number,
            section_title=header,
            content_hash=content_hash,
        )


@dataclass(slots=True)
class VoyageIngestionPipeline:
    """Runs markdown chunking + Voyage embeddings inline for reduced scope."""

    voyage_client: VoyageEmbeddingClientProtocol
    chunker: MarkdownChunker
    worker_name: str = "agent-api-inline"

    async def ingest_document(
        self,
        *,
        document: Document,
        upload_payload: DocumentUploadData,
        session: AsyncSession,
    ) -> IngestionJobSummary:
        chunks = self.chunker.chunk(str(document.id), upload_payload.content)
        if not chunks:
            raise ValueError("Document content did not yield any chunks")
        texts = [chunk.content for chunk in chunks]
        embeddings = await self.voyage_client.embed(texts)
        if len(embeddings) != len(chunks):  # pragma: no cover - defensive
            raise RuntimeError("Voyage embedding count mismatch")

        owner_id = document.owner_user_id
        country_code = (document.country_code or upload_payload.country_code or "UNK").upper()
        metadata = self._chunk_metadata(upload_payload.metadata)

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk_id = uuid4()
            chunk_row = Chunk(
                id=chunk_id,
                document_id=document.id,
                position=chunk.chunk_index,
                chunk_type=upload_payload.chunk_type,
                page_number=chunk.page_number,
                text_content=chunk.content,
                section_path=[chunk.section_title] if chunk.section_title else None,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                owner_user_id=owner_id,
                country_code=country_code,
                metadata_=metadata,
                embedding=embedding,
            )
            session.add(chunk_row)
            session.add(
                ChunkMetrics(
                    chunk_id=chunk_id,
                    chunk_country_code=country_code,
                    quality_score=None,
                    retrieval_count=0,
                )
            )

        now = datetime.now(UTC)
        document.status = "active"
        document.ingestion_stage = "activate"
        document.ingestion_started_at = document.ingestion_started_at or now
        document.ingestion_completed_at = now

        job = IngestionJob(
            document_id=document.id,
            stage="activate",
            status="succeeded",
            worker=self.worker_name,
            started_at=now,
            completed_at=now,
        )
        session.add(job)
        await session.flush()

        await refresh_active_chunks_view(session)
        if document.access_scope == "base" and document.country_code:
            await refresh_base_documents_cache_for_country(session, document.country_code)

        return IngestionJobSummary(
            id=job.id,
            document_id=job.document_id,
            stage=job.stage,
            status=job.status,
            started_at=job.started_at or now,
            completed_at=job.completed_at or now,
        )

    def _chunk_metadata(self, metadata: dict[str, object] | None) -> dict[str, object]:
        payload = dict(metadata or {})
        ingestion_meta = payload.setdefault("ingestion", {})  # type: ignore[assignment]
        if isinstance(ingestion_meta, dict):
            ingestion_meta.setdefault("mode", "voyage")
            ingestion_meta.setdefault("source", "document_upload")
        else:
            payload["ingestion"] = {"mode": "voyage", "source": "document_upload"}
        return payload


__all__ = ["ChunkPayload", "MarkdownChunker", "VoyageIngestionPipeline"]
