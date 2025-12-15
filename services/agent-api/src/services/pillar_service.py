"""Synchronous pillar aggregation helpers for reduced-scope mode."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from shared_data_layer.db.models.retrieval import PillarAnswer, PillarAnswerSource
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from repositories.conversation_scope_repository import ConversationScopeRepository


@dataclass(slots=True)
class PillarSourceDTO:
    chunk_id: str
    document_id: str | None
    chunk_type: str | None
    evidence_text: str
    page_number: int | None


@dataclass(slots=True)
class PillarAnswerDTO:
    pillar: str
    score: float | None
    summary_markdown: str
    answer_json: dict[str, Any]
    country_code: str
    document_id: str
    generated_at: datetime | None
    sources: list[PillarSourceDTO]


class PillarService:
    """Queries pillar answers constrained to allowed chunk types."""

    def __init__(
        self,
        session,
        *,
        allowed_chunk_types: Sequence[str] | None = None,
    ) -> None:
        self._session = session
        self._scope_repo = ConversationScopeRepository(session)
        normalized = tuple(ct.lower() for ct in (allowed_chunk_types or ("text",)))
        self._allowed_chunk_types = normalized or ("text",)

    async def list_for_country(self, country_code: str) -> list[PillarAnswerDTO]:
        stmt = (
            select(PillarAnswer)
            .where(PillarAnswer.country_code == country_code.upper())
            .where(PillarAnswer.status == "published")
            .options(selectinload(PillarAnswer.sources).selectinload(PillarAnswerSource.chunk))
            .order_by(PillarAnswer.pillar_name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_dto(row) for row in rows]

    async def list_for_conversation(self, conversation_id: str | UUID) -> ConversationPillarResult:
        conversation = await self._scope_repo.fetch_conversation(conversation_id)
        if conversation is None:
            raise LookupError("Conversation not found")
        attachments = await self._scope_repo.list_conversation_documents(conversation_id)
        doc_ids = [UUID(record.document_id) for record in attachments]
        if not doc_ids:
            return ConversationPillarResult(country_code=conversation.country_code, answers=[])
        stmt = (
            select(PillarAnswer)
            .where(PillarAnswer.document_id.in_(doc_ids))
            .where(PillarAnswer.status == "published")
            .options(selectinload(PillarAnswer.sources).selectinload(PillarAnswerSource.chunk))
            .order_by(PillarAnswer.pillar_name)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return ConversationPillarResult(
            country_code=conversation.country_code,
            answers=[self._to_dto(row) for row in rows],
        )

    def _to_dto(self, answer: PillarAnswer) -> PillarAnswerDTO:
        sources = [
            self._to_source_dto(source)
            for source in answer.sources
            if self._is_source_allowed(source)
        ]
        return PillarAnswerDTO(
            pillar=answer.pillar_name,
            score=answer.score,
            summary_markdown=answer.summary_markdown,
            answer_json=dict(answer.answer_json or {}),
            country_code=answer.country_code,
            document_id=str(answer.document_id),
            generated_at=answer.generated_at,
            sources=sources,
        )

    def _to_source_dto(self, source: PillarAnswerSource) -> PillarSourceDTO:
        chunk = source.chunk
        document_id = str(chunk.document_id) if chunk and chunk.document_id else None
        chunk_type = chunk.chunk_type if chunk else None
        return PillarSourceDTO(
            chunk_id=str(source.chunk_id),
            document_id=document_id,
            chunk_type=chunk_type,
            evidence_text=source.evidence_text,
            page_number=source.page_number,
        )

    def _is_source_allowed(self, source: PillarAnswerSource) -> bool:
        chunk = source.chunk
        if chunk is None:
            return False
        return chunk.chunk_type.lower() in self._allowed_chunk_types


__all__ = [
    "ConversationPillarResult",
    "PillarAnswerDTO",
    "PillarService",
    "PillarSourceDTO",
]


@dataclass(slots=True)
class ConversationPillarResult:
    country_code: str | None
    answers: list[PillarAnswerDTO]
