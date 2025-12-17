"""Query helpers around conversation/document scope and hybrid retrieval."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

import numpy as np
from pgvector.vector import Vector as PgVector
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import ConversationDocument, Document
from shared_data_layer.db.models.retrieval import Chunk
from shared_data_layer.repositories.documents import DocumentRepository
from sqlalchemy import bindparam, func, select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConversationDocumentRecord:
    document_id: str
    attach_source: str
    role: str
    visibility: Literal["visible", "hidden", "read_only"]
    canonical_name: str | None
    access_scope: str
    country_code: str | None
    metadata: dict[str, Any] | None

    @property
    def read_only(self) -> bool:
        return self.visibility == "read_only"

    @property
    def is_visible(self) -> bool:
        return self.visibility != "hidden"


@dataclass(slots=True)
class DocumentSummary:
    document_id: str
    canonical_name: str | None
    access_scope: str
    country_code: str | None
    language: str | None
    status: str
    tags: list[str] | None
    metadata: dict[str, Any] | None

    @property
    def auto_attach_enabled(self) -> bool:
        metadata = self.metadata or {}
        return metadata.get("auto_attach_enabled", True)


@dataclass(slots=True)
class DocumentChunkPreview:
    document_id: str
    chunk_id: str
    text: str
    page_number: int | None = None
    position: int | None = None
    score: float | None = None
    canonical_name: str | None = None


class ConversationScopeRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._document_repo = DocumentRepository(session)

    async def fetch_conversation(self, conversation_id: str | UUID) -> Conversation | None:
        return await self._session.get(Conversation, _as_uuid(conversation_id))

    async def list_conversation_documents(
        self, conversation_id: str | UUID
    ) -> list[ConversationDocumentRecord]:
        stmt = (
            select(
                ConversationDocument.document_id,
                ConversationDocument.attach_source,
                ConversationDocument.role,
                ConversationDocument.visibility_override,
                Document.canonical_name,
                Document.access_scope,
                Document.country_code,
                Document.metadata_,
            )
            .join(Document, Document.id == ConversationDocument.document_id)
            .where(ConversationDocument.conversation_id == _as_uuid(conversation_id))
            .where(ConversationDocument.deleted_at.is_(None))
        )
        rows = await self._session.execute(stmt)
        records: list[ConversationDocumentRecord] = []
        for row in rows:
            raw_visibility = row.visibility_override or "visible"
            visibility = _normalize_visibility(raw_visibility)
            records.append(
                ConversationDocumentRecord(
                    document_id=str(row.document_id),
                    attach_source=row.attach_source,
                    role=row.role,
                    visibility=visibility,
                    canonical_name=row.canonical_name,
                    access_scope=row.access_scope,
                    country_code=row.country_code,
                    metadata=row.metadata_,
                )
            )
        return records

    async def ensure_attachment(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
        attach_source: str,
        role: str = "primary",
        visibility_override: str | None = None,
        attached_by_user_id: str | UUID | None = None,
    ) -> ConversationDocumentRecord:
        attachment = await self._document_repo.attach_to_conversation(
            conversation_id=_as_uuid(conversation_id),
            document_id=_as_uuid(document_id),
            attach_source=attach_source,
            role=role,
            attached_by_user_id=_as_uuid(attached_by_user_id) if attached_by_user_id else None,
            visibility_override=visibility_override,
        )
        document = await self._document_repo.get(_as_uuid(document_id))
        metadata = document.metadata_ if document else None
        visibility = _normalize_visibility(attachment.visibility_override or "visible")
        return ConversationDocumentRecord(
            document_id=str(attachment.document_id),
            attach_source=attachment.attach_source,
            role=attachment.role,
            visibility=visibility,
            canonical_name=document.canonical_name if document else None,
            access_scope=document.access_scope if document else "user_private",
            country_code=document.country_code if document else None,
            metadata=metadata,
        )

    async def hydrate_documents(
        self, document_ids: Iterable[str | UUID]
    ) -> dict[str, DocumentSummary]:
        uuids = [_as_uuid(doc_id) for doc_id in document_ids]
        if not uuids:
            return {}
        stmt = select(Document).where(Document.id.in_(uuids))
        rows = (await self._session.execute(stmt)).scalars().all()
        return {str(row.id): self._map_document(row) for row in rows}

    async def load_document_chunk_previews(
        self,
        document_ids: Iterable[str | UUID],
        *,
        chunk_types: Sequence[str] = ("text",),
        max_chars_per_doc: int = 1600,
        max_chunks_per_doc: int = 5,
    ) -> dict[str, list[DocumentChunkPreview]]:
        uuids = [_as_uuid(doc_id) for doc_id in document_ids]
        if not uuids:
            return {}
        stmt = (
            select(
                Chunk.document_id,
                Chunk.id,
                Chunk.position,
                Chunk.text_content,
                Chunk.page_number,
                Chunk.chunk_type,
            )
            .where(Chunk.document_id.in_(uuids))
            .order_by(Chunk.document_id, Chunk.position)
        )
        if chunk_types:
            stmt = stmt.where(Chunk.chunk_type.in_(tuple(chunk_types)))
        rows = await self._session.execute(stmt)
        previews: dict[str, list[DocumentChunkPreview]] = {}
        char_counts: dict[str, int] = {}
        chunk_counts: dict[str, int] = {}
        for row in rows:
            doc_id = str(row.document_id)
            text = (row.text_content or "").strip()
            if not text:
                continue
            if chunk_counts.get(doc_id, 0) >= max_chunks_per_doc:
                continue
            remaining = max_chars_per_doc - char_counts.get(doc_id, 0)
            if remaining <= 0:
                continue
            snippet = text if len(text) <= remaining else text[:remaining]
            previews.setdefault(doc_id, []).append(
                DocumentChunkPreview(
                    document_id=doc_id,
                    chunk_id=str(row.id),
                    text=snippet,
                    page_number=row.page_number,
                    position=row.position,
                )
            )
            char_counts[doc_id] = char_counts.get(doc_id, 0) + len(snippet)
            chunk_counts[doc_id] = chunk_counts.get(doc_id, 0) + 1
        return previews

    async def hybrid_chunk_search(  # noqa: PLR0912
        self,
        *,
        query: str,
        document_ids: Iterable[str | UUID],
        embedding: Sequence[float] | None = None,
        top_k: int = 8,
        hybrid_weight: float = 0.5,
        chunk_types: Sequence[str] = ("text",),
    ) -> dict[str, list[DocumentChunkPreview]]:
        uuids = [_as_uuid(doc_id) for doc_id in document_ids]
        if not uuids or not query:
            return {}

        chunk_select = (
            select(
                Chunk.document_id,
                Chunk.id,
                Chunk.position,
                Chunk.text_content,
                Chunk.page_number,
                Chunk.chunk_type,
            )
            .where(Chunk.document_id.in_(uuids))
            .where(Chunk.text_content.is_not(None))
        )
        if chunk_types:
            chunk_select = chunk_select.where(Chunk.chunk_type.in_(tuple(chunk_types)))

        tsquery = func.websearch_to_tsquery("english", query)
        bm25_expr = func.ts_rank_cd(Chunk.text_tsv, tsquery).label("bm25")
        bm25_stmt = chunk_select.add_columns(bm25_expr).order_by(bm25_expr.desc())
        bm25_rows = (await self._session.execute(bm25_stmt.limit(max(top_k * 3, 10)))).all()
        vector_rows = []
        vector_scores: dict[str, float] = {}
        vector_embedding = _coerce_embedding(embedding) if embedding is not None else None
        if vector_embedding:
            embedding_array = np.asarray(vector_embedding, dtype=">f4")
            if embedding_array.ndim != 1:
                raise ValueError(
                    f"embedding must be 1D, received ndim={embedding_array.ndim} shape={embedding_array.shape}"
                )
            normalized_embedding = embedding_array.tolist()
            pgvector_embedding = PgVector(normalized_embedding)
            embedding_param = bindparam(
                "embedding_vec", pgvector_embedding, type_=Chunk.embedding.type
            )
            distance_expr = Chunk.embedding.cosine_distance(embedding_param)
            vector_stmt = chunk_select.add_columns(distance_expr.label("vector_score")).order_by(
                distance_expr
            )
            try:
                vector_rows = (
                    await self._session.execute(vector_stmt.limit(max(top_k * 3, 10)))
                ).all()
            except StatementError as exc:
                logger.error("hybrid_chunk_search.statement_error params=%s", exc.params)
                raise
            for row in vector_rows:
                distance = float(row.vector_score or 0.0)
                similarity = max(0.0, 1.0 - distance)
                vector_scores[str(row.id)] = similarity

        bm25_scores: dict[str, float] = {}
        for row in bm25_rows:
            bm25_scores[str(row.id)] = float(row.bm25 or 0.0)

        max_bm25 = max(bm25_scores.values() or [1.0])
        max_vector = max(vector_scores.values() or [1.0])

        combined: dict[str, float] = {}
        for chunk_id in set(bm25_scores.keys()) | set(vector_scores.keys()):
            bm25_component = bm25_scores.get(chunk_id, 0.0) / max_bm25 if max_bm25 else 0.0
            vector_component = vector_scores.get(chunk_id, 0.0) / max_vector if max_vector else 0.0
            combined[chunk_id] = (
                hybrid_weight * vector_component + (1.0 - hybrid_weight) * bm25_component
            )

        scored_rows = {str(row.id): row for row in bm25_rows}
        for row in vector_rows:
            scored_rows.setdefault(str(row.id), row)

        sorted_ids = sorted(combined.keys(), key=lambda cid: combined[cid], reverse=True)
        selected_ids = set(sorted_ids[: top_k * 2])

        per_doc: dict[str, list[DocumentChunkPreview]] = {}
        for chunk_id in sorted_ids:
            if chunk_id not in selected_ids:
                continue
            row = scored_rows.get(chunk_id)
            if row is None:
                continue
            doc_id = str(row.document_id)
            text = (row.text_content or "").strip()
            if not text:
                continue
            per_doc.setdefault(doc_id, [])
            if len(per_doc[doc_id]) >= top_k:
                continue
            per_doc[doc_id].append(
                DocumentChunkPreview(
                    document_id=doc_id,
                    chunk_id=str(row.id),
                    text=text,
                    page_number=row.page_number,
                    position=row.position,
                    score=combined.get(chunk_id),
                )
            )
        return per_doc

    def _map_document(self, document: Document) -> DocumentSummary:
        metadata = document.metadata_ if document is not None else None
        return DocumentSummary(
            document_id=str(document.id),
            canonical_name=document.canonical_name,
            access_scope=document.access_scope,
            country_code=document.country_code,
            language=document.language,
            status=document.status,
            tags=document.tags,
            metadata=metadata,
        )


@runtime_checkable
class ConversationScopePort(Protocol):
    async def list_conversation_documents(
        self, conversation_id: str | UUID
    ) -> list[ConversationDocumentRecord]: ...

    async def ensure_attachment(
        self,
        *,
        conversation_id: str | UUID,
        document_id: str | UUID,
        attach_source: str,
        role: str = "primary",
        visibility_override: str | None = None,
        attached_by_user_id: str | UUID | None = None,
    ) -> ConversationDocumentRecord: ...

    async def hydrate_documents(
        self, document_ids: Iterable[str | UUID]
    ) -> dict[str, DocumentSummary]: ...

    async def load_document_chunk_previews(
        self,
        document_ids: Iterable[str | UUID],
        *,
        chunk_types: Sequence[str] = ("text",),
        max_chars_per_doc: int = 1600,
        max_chunks_per_doc: int = 5,
    ) -> dict[str, list[DocumentChunkPreview]]: ...

    async def hybrid_chunk_search(
        self,
        *,
        query: str,
        document_ids: Iterable[str | UUID],
        embedding: Sequence[float] | None = None,
        top_k: int = 8,
        hybrid_weight: float = 0.5,
        chunk_types: Sequence[str] = ("text",),
    ) -> dict[str, list[DocumentChunkPreview]]: ...


def _as_uuid(value: str | UUID | None) -> UUID:
    if value is None:
        raise ValueError("Expected UUID value, received None")
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _normalize_visibility(raw: str) -> Literal["visible", "hidden", "read_only"]:
    value = (raw or "visible").strip().lower()
    if value not in {"visible", "hidden", "read_only"}:
        return "visible"
    return value  # type: ignore[return-value]


def _coerce_embedding(embedding: Sequence[float]) -> list[float]:
    if isinstance(embedding, (str, bytes, dict)):
        raise ValueError(f"embedding must be a 1D sequence of floats, received {type(embedding)}")
    if any(isinstance(item, Sequence) and not isinstance(item, (str, bytes)) for item in embedding):
        raise ValueError("embedding must be flat (1D) and cannot contain nested sequences")
    try:
        vector = [float(x) for x in embedding]
    except Exception as exc:  # pragma: no cover
        raise ValueError("Failed to coerce embedding into floats") from exc
    if not vector:
        raise ValueError("embedding must not be empty")
    return vector


__all__ = [
    "ConversationDocumentRecord",
    "ConversationScopePort",
    "ConversationScopeRepository",
    "DocumentChunkPreview",
    "DocumentSummary",
]
