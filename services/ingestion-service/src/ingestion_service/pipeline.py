from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import UUID, uuid4

from markitdown import FileConversionException, MarkItDown, UnsupportedFormatException
from shared_data_layer.config import SYSTEM_OWNER_SENTINEL
from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.documents import Document, IngestionJob
from shared_data_layer.db.models.retrieval import Chunk, ChunkMetrics
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from ingestion_service.embeddings import (
    VoyageEmbeddingClient,
    VoyageEmbeddingClientProtocol,
)
from ingestion_service.settings import ALLOWED_VOYAGE_OUTPUT_DIMENSIONS, Settings
from ingestion_service.schemas import UploadInitRequest

logger = logging.getLogger(__name__)


class IngestionError(RuntimeError):
    """Raised when ingestion fails and document should be marked failed."""


@dataclass(slots=True)
class ChunkPayload:
    content: str
    chunk_index: int
    token_count: int
    page_number: int | None
    section_title: str | None
    content_hash: str
    contextual_text: str
    propositions: list[str]


class MarkdownChunker:
    """Simple markdown chunker mirroring the agent-api embedding writer."""

    TARGET_TOKENS = 500
    # Keep max at or below DB constraint ck_chunks_token_limit (800)
    MAX_TOKENS = 800
    MIN_TOKENS = 50
    OVERLAP_TOKENS = 50
    CHARS_PER_TOKEN = 4

    PAGE_PATTERN = re.compile(r"^##?\s+Page\s+(?P<page>\d+)", re.IGNORECASE)
    HEADER_PATTERN = re.compile(r"^#{1,3}\s+(?P<header>.+)")
    SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")

    def chunk(self, document_id: str, content: str) -> list[ChunkPayload]:
        if not content.strip():
            return []
        segments = re.split(r"(\n##?\s+Page\s+\d+|\n#{1,3}\s+[^\n]+)", content)
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

        if (
            current_text.strip()
            and self._token_estimate(current_text) >= self.MIN_TOKENS
        ):
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
        propositions = self._propositionize(normalized)
        return ChunkPayload(
            content=normalized,
            chunk_index=chunk_index,
            token_count=token_count,
            page_number=page_number,
            section_title=header,
            content_hash=content_hash,
            contextual_text=self._build_contextual_text(
                normalized,
                header=header,
                page_number=page_number,
                propositions=propositions,
            ),
            propositions=propositions,
        )

    def _build_contextual_text(
        self,
        text: str,
        *,
        header: str | None,
        page_number: int | None,
        propositions: list[str],
    ) -> str:
        """
        Create a contextualized chunk string with lightweight HyPE/HyDE-style rewrites.
        Uses deterministic heuristics (no LLM calls) to keep ingestion synchronous.
        """
        parts: list[str] = []
        if header:
            parts.append(f"Section: {header.strip()}")
        if page_number:
            parts.append(f"Page: {page_number}")
        if propositions:
            parts.append("Propositions:")
            parts.extend(f"- {p}" for p in propositions[:3])
            parts.append(f"Hypothesis: {propositions[0]}")
        parts.append("Content:")
        parts.append(text)
        return "\n".join(parts)

    def _propositionize(self, text: str) -> list[str]:
        sentences = [
            s.strip()
            for s in self.SENTENCE_PATTERN.split(text)
            if s and len(s.strip()) > 12
        ]
        if not sentences and text:
            return [text[:200].strip()]
        propositions: list[str] = []
        for sentence in sentences:
            clean = re.sub(r"\s+", " ", sentence).strip().rstrip(".")
            if clean:
                propositions.append(clean)
            if len(propositions) >= 4:
                break
        return propositions


class MarkdownConverter:
    """Wraps MarkItDown with a conversion convenience helper."""

    def __init__(self) -> None:
        self._converter = MarkItDown()

    def convert(self, *, data: bytes, suffix: str) -> tuple[str, dict[str, Any]]:
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            path = tmp.name
        try:
            result = self._converter.convert(path)
        except (UnsupportedFormatException, FileConversionException) as exc:
            raise IngestionError(f"Conversion failed: {exc}") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                logger.warning("Failed to cleanup temp file %s", path)

        markdown = getattr(result, "text_content", None) or getattr(
            result, "markdown_content", None
        )
        if not markdown or not markdown.strip():
            raise IngestionError("Conversion returned empty content")
        metadata = getattr(result, "metadata", {}) or {}
        return markdown.strip(), metadata


class IngestionPipeline:
    """End-to-end ingestion pipeline (convert + chunk + embed + activate)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._chunker = MarkdownChunker()
        self._converter = MarkdownConverter()
        self._storage_dimension = settings.vector_store_dimension
        self._default_output_dimension = settings.voyage_output_dimension
        if self._default_output_dimension != self._storage_dimension:
            raise ValueError(
                "voyage_output_dimension must align with vector_store_dimension/EMBEDDING_DIMENSION "
                f"({self._storage_dimension}). Set VOYAGE_OUTPUT_DIMENSION/VOYAGE_EMBEDDING_DIM "
                "to the pgvector column dimension (256/512/1024/2048)."
            )
        self._voyage: VoyageEmbeddingClientProtocol | None = None
        if settings.voyage_api_key:
            self._voyage = VoyageEmbeddingClient(
                api_key=settings.voyage_api_key,
                model=settings.voyage_model,
            )

    async def ingest_file(
        self,
        *,
        session: AsyncSession,
        request: UploadInitRequest,
        owner_user_id: UUID | None,
        document_id: UUID,
        ingestion_id: UUID | None,
        file_bytes: bytes,
    ) -> tuple[Document, IngestionJob]:
        output_dimension = self._resolve_output_dimension(request.output_dimension)
        request.output_dimension = output_dimension  # ensure downstream consistency
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        existing = await self._find_duplicate(
            session=session,
            owner_user_id=owner_user_id,
            access_scope=request.access_scope,
            content_hash=content_hash,
            country_code=request.country_code,
        )
        if existing:
            logger.info(
                "Deduped upload for hash=%s (document %s)",
                content_hash[:8],
                existing.id,
            )
            job = await self._record_job(
                session=session,
                document_id=existing.id,
                stage="activate",
                status="succeeded",
                metadata={"deduped": True},
                job_id=ingestion_id,
            )
            return existing, job

        document = await self._create_document(
            session=session,
            request=request,
            owner_user_id=owner_user_id,
            content_hash=content_hash,
            byte_size=len(file_bytes),
            document_id=document_id,
            ingestion_id=ingestion_id,
            output_dimension=output_dimension,
        )

        try:
            markdown, conversion_meta = self._converter.convert(
                data=file_bytes,
                suffix=request.source_type,
            )
            await self._update_stage(
                session=session,
                document=document,
                stage="chunk",
                metadata={"conversion": conversion_meta},
            )
            job = await self._write_chunks_and_embeddings(
                session=session,
                document=document,
                markdown=markdown,
                request=request,
                ingestion_id=ingestion_id,
            )
            await refresh_active_chunks_view(session)
            if document.access_scope == "base" and document.country_code:
                await refresh_base_documents_cache_for_country(
                    session, document.country_code
                )
            return document, job
        except RetryError as exc:
            await self._fail_document(
                session=session,
                document=document,
                stage=document.ingestion_stage or "convert",
                ingestion_id=ingestion_id,
                reason=f"Retry exhaustion: {exc}",
            )
            raise
        except Exception as exc:
            await self._fail_document(
                session=session,
                document=document,
                stage=document.ingestion_stage or "convert",
                ingestion_id=ingestion_id,
                reason=str(exc),
            )
            raise

    async def _find_duplicate(
        self,
        *,
        session: AsyncSession,
        owner_user_id: UUID | None,
        access_scope: str,
        content_hash: str,
        country_code: str | None,
    ) -> Document | None:
        stmt = select(Document).where(Document.content_hash == content_hash)
        stmt = stmt.where(Document.deleted_at.is_(None))
        if access_scope == "base":
            stmt = stmt.where(Document.access_scope == "base")
            stmt = stmt.where(Document.owner_user_id.in_([None, SYSTEM_OWNER_SENTINEL]))
            if country_code:
                stmt = stmt.where(Document.country_code == country_code)
        else:
            stmt = stmt.where(Document.access_scope == access_scope)
            stmt = stmt.where(Document.owner_user_id == owner_user_id)
        result = await session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def _create_document(
        self,
        *,
        session: AsyncSession,
        request: UploadInitRequest,
        owner_user_id: UUID | None,
        content_hash: str,
        byte_size: int,
        document_id: UUID,
        ingestion_id: UUID | None,
        output_dimension: int,
    ) -> Document:
        now = datetime.now(UTC)
        if request.access_scope == "user_private" and owner_user_id is None:
            raise IngestionError("owner_user_id is required for user-private documents")
        if request.access_scope == "base" and owner_user_id not in (
            None,
            SYSTEM_OWNER_SENTINEL,
        ):
            raise IngestionError(
                "Base documents cannot set owner_user_id (except shared sentinel)"
            )

        metadata = dict(request.metadata)
        ingestion_meta = metadata.setdefault("ingestion", {})  # type: ignore[assignment]
        if isinstance(ingestion_meta, dict):
            ingestion_meta.setdefault("mode", "text_sync_contextual")
            ingestion_meta.setdefault("model", self._settings.voyage_model)
            ingestion_meta.setdefault("output_dimension", output_dimension)
            ingestion_meta.setdefault("source_type", request.source_type)
            if ingestion_id:
                ingestion_meta.setdefault("ingestion_id", str(ingestion_id))
        else:
            metadata["ingestion"] = {
                "mode": "text_sync_contextual",
                "model": self._settings.voyage_model,
                "output_dimension": output_dimension,
                "source_type": request.source_type,
                "ingestion_id": str(ingestion_id) if ingestion_id else None,
            }

        document = Document(
            id=document_id,
            owner_user_id=owner_user_id,
            access_scope=request.access_scope,
            canonical_name=request.document_name,
            country_code=request.country_code,
            language=request.language,
            tags=request.tags or None,
            status="ingesting",
            ingestion_stage="convert",
            ingestion_started_at=now,
            ingestion_completed_at=None,
            content_hash=content_hash,
            source_uri=None,
            byte_size=byte_size,
            visibility=self._derive_visibility(request.access_scope),
            managed_by="system" if request.access_scope == "base" else "user",
            metadata_=metadata,
        )
        session.add(document)
        await session.flush()
        return document

    async def _update_stage(
        self,
        *,
        session: AsyncSession,
        document: Document,
        stage: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        document.ingestion_stage = stage
        if metadata:
            payload = dict(document.metadata_ or {})
            existing = payload.setdefault("ingestion", {})
            if isinstance(existing, dict):
                existing.update(metadata)
                document.metadata_ = payload
        await session.flush()

    async def _write_chunks_and_embeddings(
        self,
        *,
        session: AsyncSession,
        document: Document,
        markdown: str,
        request: UploadInitRequest,
        ingestion_id: UUID | None,
    ) -> IngestionJob:
        chunks = self._chunker.chunk(str(document.id), markdown)
        if not chunks:
            raise IngestionError("No chunks produced from markdown")

        output_dimension = self._resolve_output_dimension(request.output_dimension)
        embedding_meta = {
            "model": self._settings.voyage_model,
            "output_dimension": output_dimension,
            "input_type": "document",
            "contextualized": True,
            "normalized": True,
        }
        await self._update_stage(
            session=session,
            document=document,
            stage="embed",
            metadata={"embedding": embedding_meta},
        )
        embeddings: Sequence[Sequence[float]] | None = None
        if self._voyage:
            embeddings = await self._voyage.embed(
                [chunk.contextual_text for chunk in chunks],
                output_dimension=output_dimension,
                input_type="document",
            )
            if len(embeddings) != len(chunks):
                raise IngestionError("Embedding count mismatch")

        owner_id = document.owner_user_id
        country_code = (document.country_code or request.country_code or "UNK").upper()
        base_metadata = self._chunk_metadata(
            document.metadata_
            if isinstance(document.metadata_, dict)
            else request.metadata,
            embedding_meta=embedding_meta,
            chunk_strategy={
                "method": "markdown_headers_with_overlap",
                "target_tokens": self._chunker.TARGET_TOKENS,
                "overlap_tokens": self._chunker.OVERLAP_TOKENS,
                "max_tokens": self._chunker.MAX_TOKENS,
            },
        )

        for idx, chunk in enumerate(chunks):
            chunk_id = uuid4()
            embedding = embeddings[idx] if embeddings else None
            chunk_metadata = dict(base_metadata)
            chunk_chunking = chunk_metadata.setdefault("chunking", {})  # type: ignore[assignment]
            if isinstance(chunk_chunking, dict):
                chunk_chunking.setdefault("section_title", chunk.section_title)
                chunk_chunking.setdefault("page_number", chunk.page_number)
                chunk_chunking.setdefault("propositions", chunk.propositions)
            chunk_row = Chunk(
                id=chunk_id,
                document_id=document.id,
                position=chunk.chunk_index,
                chunk_type="text",
                page_number=chunk.page_number,
                text_content=chunk.content,
                section_path=[chunk.section_title] if chunk.section_title else None,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                owner_user_id=owner_id,
                country_code=country_code,
                metadata_=chunk_metadata,
                embedding=list(map(float, embedding)) if embedding else None,
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

        job = await self._record_job(
            session=session,
            document_id=document.id,
            stage="activate",
            status="succeeded",
            metadata={"source": "text_sync_contextual", "embedding": embedding_meta},
            job_id=ingestion_id,
        )
        return job

    async def _record_job(
        self,
        *,
        session: AsyncSession,
        document_id: UUID,
        stage: str,
        status: str,
        metadata: dict[str, Any] | None = None,
        job_id: UUID | None = None,
    ) -> IngestionJob:
        now = datetime.now(UTC)
        job = IngestionJob(
            id=job_id or uuid4(),
            document_id=document_id,
            stage=stage,
            status=status,
            attempt=1,
            worker=self._settings.worker_name,
            last_error=metadata if status == "failed" else None,
            started_at=now,
            completed_at=now,
        )
        session.add(job)
        await session.flush()
        return job

    async def _fail_document(
        self,
        *,
        session: AsyncSession,
        document: Document,
        stage: str,
        ingestion_id: UUID | None,
        reason: str,
    ) -> None:
        now = datetime.now(UTC)
        document.status = "failed"
        document.ingestion_stage = stage
        document.ingestion_completed_at = now

        payload = dict(document.metadata_ or {})
        failure_meta = payload.setdefault("ingestion_failure", {})
        if isinstance(failure_meta, dict):
            failure_meta["reason"] = reason
            failure_meta["at"] = now.isoformat()
            document.metadata_ = payload

        await self._record_job(
            session=session,
            document_id=document.id,
            stage=stage,
            status="failed",
            metadata={"reason": reason},
            job_id=ingestion_id,
        )

    @staticmethod
    def _chunk_metadata(
        metadata: dict[str, Any] | None,
        *,
        embedding_meta: dict[str, Any],
        chunk_strategy: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(metadata or {})
        ingestion_meta = payload.setdefault("ingestion", {})  # type: ignore[assignment]
        if isinstance(ingestion_meta, dict):
            ingestion_meta.setdefault("mode", "text_sync_contextual")
            ingestion_meta.setdefault("source", "document_upload")
            ingestion_meta.setdefault("embedding", embedding_meta)
            ingestion_meta.setdefault("chunking", chunk_strategy)
        else:
            payload["ingestion"] = {
                "mode": "text_sync_contextual",
                "source": "document_upload",
                "embedding": embedding_meta,
                "chunking": chunk_strategy,
            }
        return payload

    @staticmethod
    def _derive_visibility(access_scope: str) -> str:
        if access_scope == "user_shared":
            return "shared"
        if access_scope == "base":
            return "base_admin"
        return "private"

    def _resolve_output_dimension(self, requested: int | None) -> int:
        """
        Ensure the requested output dimension is supported and matches the vector store shape.
        """
        dimension = requested or self._default_output_dimension
        if dimension not in ALLOWED_VOYAGE_OUTPUT_DIMENSIONS:
            raise IngestionError(
                f"output_dimension must be one of {ALLOWED_VOYAGE_OUTPUT_DIMENSIONS}"
            )
        if dimension != self._storage_dimension:
            raise IngestionError(
                f"output_dimension {dimension} must match vector_store_dimension {self._storage_dimension}"
            )
        return dimension
