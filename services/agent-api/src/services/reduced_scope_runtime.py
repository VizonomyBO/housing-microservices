"""Workerless runtime helpers for reduced-scope operation."""

from __future__ import annotations

import hashlib
import logging
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from shared_data_layer.db.maintenance import (
    refresh_active_chunks_view,
    refresh_base_documents_cache_for_country,
)
from shared_data_layer.db.models.conversations import Conversation
from shared_data_layer.db.models.documents import Artifact, Document
from shared_data_layer.db.models.retrieval import Chunk, PillarAnswer, PillarAnswerSource
from shared_data_layer.repositories.retrieval import PillarAnswerRepository
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.conversation_scope_repository import ConversationScopeRepository
from services.ingestion_job_service import IngestionJobSummary, ReducedScopeIngestionJobService
from services.pillar_service import PillarService

logger = logging.getLogger(__name__)

DEMO_PILLAR_NAMES: tuple[str, ...] = ("revenues", "transparency", "compliance")


@dataclass(slots=True)
class IngestionCompletionPayload:
    """Options for synchronous ingestion completion."""

    chunk_type: str = "text"
    metadata: dict[str, Any] | None = None
    refresh_active_chunks: bool = True
    refresh_base_documents: bool = True


@dataclass(slots=True)
class PillarGenerationRequest:
    country_code: str | None = None
    conversation_id: str | UUID | None = None
    pillars: Sequence[str] | None = None
    max_sources: int = 3


@dataclass(slots=True)
class ArtifactGenerationRequest:
    conversation_id: str | UUID
    artifact_type: str
    metadata: dict[str, Any] | None = None


class ReducedScopeWorkerRuntime:
    """Executes ingestion, pillar, and artifact flows synchronously."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        ingestion_service: ReducedScopeIngestionJobService,
        pillar_service: PillarService,
        allowed_chunk_types: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        self._ingestion = ingestion_service
        self._pillar_service = pillar_service
        self._scope_repo = ConversationScopeRepository(session)
        normalized = tuple(ct.lower() for ct in (allowed_chunk_types or ("text",)))
        self._allowed_chunk_types = normalized or ("text",)

    async def complete_ingestion_job(
        self,
        document_id: str | UUID,
        *,
        payload: IngestionCompletionPayload | None = None,
    ) -> IngestionJobSummary:
        """Finalize ingestion bookkeeping and refresh read models."""

        completion = payload or IngestionCompletionPayload()
        summary = await self._ingestion.auto_complete(
            document_id=_as_uuid(document_id),
            chunk_type=completion.chunk_type,
            metadata=completion.metadata,
        )

        doc = await self._session.get(Document, summary.document_id)
        if completion.refresh_active_chunks:
            await refresh_active_chunks_view(self._session)
        if completion.refresh_base_documents and doc and doc.country_code:
            await refresh_base_documents_cache_for_country(self._session, doc.country_code)
        return summary

    async def generate_pillar_answers(
        self,
        *,
        country_code: str | None = None,
        conversation_id: str | UUID | None = None,
        pillars: Sequence[str] | None = None,
        max_sources: int = 3,
    ) -> list[PillarAnswer]:
        """Materialize pillar answers inline for the requested scope."""

        request = PillarGenerationRequest(
            country_code=country_code,
            conversation_id=conversation_id,
            pillars=pillars,
            max_sources=max(1, max_sources),
        )
        scope = await self._resolve_scope(request)
        if scope is None:
            return []
        conversation, anchor_document, chunk_pool = scope
        if not chunk_pool:
            logger.info("No text chunks available for pillar generation")
            return []

        target_pillars = tuple(request.pillars or DEMO_PILLAR_NAMES)
        repo = PillarAnswerRepository(self._session)
        answers: list[PillarAnswer] = []
        owner_uuid = self._resolve_owner_uuid(conversation, anchor_document)
        country = (
            conversation.country_code if conversation else None
        ) or anchor_document.country_code
        if country:
            country = country.upper()
        if not country:
            raise ValueError("Country code required for pillar generation")

        chunk_list = [chunk for chunk in chunk_pool if self._is_chunk_allowed(chunk)]
        if not chunk_list:
            logger.info("Filtered chunk pool is empty; skipping pillar generation")
            return []

        if request.pillars is None:
            existing_stmt = (
                select(PillarAnswer)
                .where(PillarAnswer.owner_user_id == owner_uuid)
                .where(PillarAnswer.country_code == country)
                .where(PillarAnswer.status == "published")
            )
            result = await self._session.execute(existing_stmt)
            existing = list(result.scalars().all())
            if existing:
                return existing

        for pillar_name in target_pillars:
            summary, used_chunks = self._compose_summary(
                pillar_name,
                chunk_list,
                max_sources=request.max_sources,
            )
            if not summary:
                continue
            await self._supersede_existing_answer(owner_uuid, country, pillar_name)
            answer = await repo.create_pillar_answer(
                owner_user_id=owner_uuid,
                document_id=anchor_document.id,
                country_code=country,
                pillar_name=pillar_name,
                content_hash=_hash(summary),
                summary_markdown=summary,
                answer_json={
                    "mode": "reduced_scope_demo",
                    "pillar": pillar_name,
                    "sources": [
                        {
                            "chunk_id": str(chunk.id),
                            "document_id": str(chunk.document_id),
                        }
                        for chunk in used_chunks
                    ],
                },
                status="published",
                score=self._score_from_chunks(used_chunks),
                generated_at=datetime.now(UTC),
            )
            for chunk in used_chunks:
                source = PillarAnswerSource(
                    pillar_answer_id=answer.id,
                    chunk_id=chunk.id,
                    chunk_country_code=chunk.country_code,
                    contribution_type="text",
                    weight=1.0,
                    evidence_text=(chunk.text_content or "Snippet unavailable"),
                    page_number=chunk.page_number,
                )
                self._session.add(source)
            answers.append(answer)
        await self._session.flush()
        return answers

    async def generate_artifact(
        self,
        *,
        conversation_id: str | UUID,
        artifact_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Artifact]:
        """Create placeholder artifact rows for synchronous export flows."""

        conversation = await self._scope_repo.fetch_conversation(conversation_id)
        if conversation is None:
            raise LookupError("Conversation not found")
        documents = await self._scope_repo.list_conversation_documents(conversation.id)
        if not documents:
            return []
        artifacts: list[Artifact] = []
        now = datetime.now(UTC)
        for record in documents:
            doc_uuid = _as_uuid(record.document_id)
            artifact = await self._session.scalar(
                select(Artifact)
                .where(Artifact.document_id == doc_uuid)
                .where(Artifact.artifact_type == artifact_type)
            )
            payload = {
                "reduced_scope": {
                    "status": "skipped",
                    "reason": "pdf_generation_paused",
                    "generated_at": now.isoformat(),
                }
            }
            if metadata:
                payload.setdefault("metadata", {}).update(metadata)
            if artifact is None:
                artifact = Artifact(
                    document_id=doc_uuid,
                    artifact_type=artifact_type,
                    s3_uri=f"demo://artifacts/{conversation.id}/{doc_uuid}/{artifact_type}.json",
                    byte_size=0,
                    content_hash=_hash(f"{doc_uuid}:{artifact_type}"),
                    metadata_=payload,
                )
                self._session.add(artifact)
            else:
                artifact.metadata_ = payload
            artifacts.append(artifact)
        await self._session.flush()
        return artifacts

    async def _resolve_scope(
        self, request: PillarGenerationRequest
    ) -> tuple[Conversation | None, Document, list[Chunk]] | None:
        if request.conversation_id:
            conversation = await self._scope_repo.fetch_conversation(request.conversation_id)
            if conversation is None:
                raise LookupError("Conversation not found")
            attachments = await self._scope_repo.list_conversation_documents(conversation.id)
            doc_ids = [UUID(record.document_id) for record in attachments]
        else:
            conversation = None
            if not request.country_code:
                raise ValueError("country_code or conversation_id is required")
            summaries = await self._scope_repo.list_base_documents_for_country(request.country_code)
            doc_ids = [UUID(summary.document_id) for summary in summaries]
        if not doc_ids:
            return None
        statement = select(Document).where(Document.id.in_(doc_ids))
        documents = await self._session.execute(statement)
        rows = list(documents.scalars().all())
        if not rows:
            return None
        anchor: Document = rows[0]
        chunk_statement = (
            select(Chunk)
            .where(Chunk.document_id.in_(doc_ids))
            .where(Chunk.chunk_type.in_(self._allowed_chunk_types))
            .order_by(Chunk.document_id, Chunk.position)
        )
        chunk_result = await self._session.execute(chunk_statement)
        chunk_pool = list(chunk_result.scalars().all())
        return conversation, anchor, chunk_pool

    async def _supersede_existing_answer(
        self,
        owner_user_id: UUID | None,
        country_code: str,
        pillar_name: str,
    ) -> None:
        await self._session.execute(
            update(PillarAnswer)
            .where(PillarAnswer.owner_user_id == owner_user_id)
            .where(PillarAnswer.country_code == country_code)
            .where(PillarAnswer.pillar_name == pillar_name)
            .where(PillarAnswer.status == "published")
            .values(status="superseded")
        )

    def _compose_summary(
        self,
        pillar_name: str,
        chunks: Sequence[Chunk],
        *,
        max_sources: int,
    ) -> tuple[str | None, list[Chunk]]:
        usable = [chunk for chunk in chunks if self._is_chunk_allowed(chunk)]
        if not usable:
            return None, []
        selected = list(usable[: max_sources or 1])
        excerpts = [
            (chunk.text_content or "").strip()
            for chunk in selected
            if (chunk.text_content or "").strip()
        ]
        if not excerpts:
            return None, []
        synthesized = " ".join(excerpts)
        summary = textwrap.shorten(
            f"{pillar_name.replace('_', ' ').title()} insights: {synthesized}",
            width=600,
            placeholder="…",
        )
        return summary, selected

    def _resolve_owner_uuid(
        self,
        conversation: Conversation | None,
        anchor_document: Document,
    ) -> UUID:
        owner = anchor_document.owner_user_id
        if owner is None and conversation is not None:
            owner = conversation.owner_user_id
        if owner is not None:
            return owner
        country = anchor_document.country_code or "UNK"
        seed = f"base-pillars-{country.upper()}"
        return uuid5(NAMESPACE_URL, seed)

    def _score_from_chunks(self, chunks: Sequence[Chunk]) -> float | None:
        if not chunks:
            return None
        capped = min(len(chunks) * 0.15 + 0.5, 0.95)
        return round(capped, 2)

    def _is_chunk_allowed(self, chunk: Chunk) -> bool:
        normalized = (chunk.chunk_type or "").lower()
        return normalized in self._allowed_chunk_types


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _hash(raw: str | bytes) -> str:
    data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "ArtifactGenerationRequest",
    "IngestionCompletionPayload",
    "PillarGenerationRequest",
    "ReducedScopeWorkerRuntime",
]
