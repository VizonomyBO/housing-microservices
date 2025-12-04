"""Listing helpers for conversations and documents."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_data_layer.db.models.conversations import Conversation, Message
from shared_data_layer.db.models.documents import ConversationDocument, Document
from sqlalchemy import and_, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_NAMESPACE = "reduced-e2e"


@dataclass(slots=True)
class PaginationWindow:
    page: int
    page_size: int
    total_count: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total_count


@dataclass(slots=True)
class ConversationListEntry:
    conversation_id: str
    owner_user_id: str | None
    namespace: str
    title: str | None
    country_code: str | None
    status: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None
    last_activity_at: datetime
    document_count: int


@dataclass(slots=True)
class ConversationSummary:
    conversation_id: str
    owner_user_id: str | None
    attachment_count: int
    message_count: int
    user_prompt_count: int
    last_message_at: datetime | None
    last_activity_at: datetime


@dataclass(slots=True)
class DocumentListEntry:
    document_id: str
    owner_user_id: str | None
    canonical_name: str
    access_scope: str
    country_code: str | None
    language: str | None
    tags: list[str]
    status: str
    ingestion_stage: str | None
    ingestion_started_at: datetime | None
    ingestion_completed_at: datetime | None
    content_hash: str
    created_at: datetime
    updated_at: datetime | None
    metadata: dict[str, Any] | None


@dataclass(slots=True)
class PaginatedResult:
    items: list[Any]
    pagination: PaginationWindow


class ConversationListingService:
    """Lists conversations + summary metadata scoped to a single user."""

    def __init__(
        self, session: AsyncSession, *, default_namespace: str = DEFAULT_NAMESPACE
    ) -> None:
        self._session = session
        self._default_namespace = default_namespace

    async def list_conversations(
        self,
        *,
        owner_user_id: str,
        page: int,
        page_size: int,
        tags: Sequence[str] | None = None,
        country_code: str | None = None,
    ) -> PaginatedResult:
        owner_uuid = _as_uuid(owner_user_id)
        criteria = [Conversation.owner_user_id == owner_uuid]
        if country_code:
            criteria.append(Conversation.country_code == country_code.strip().upper())
        normalized_tags = _normalize_tags(tags)
        if normalized_tags:
            criteria.append(
                Conversation.metadata_.op("@>")(cast({"tags": list(normalized_tags)}, JSONB))
            )
        doc_counts = (
            select(
                ConversationDocument.conversation_id.label("conversation_id"),
                func.count()
                .filter(ConversationDocument.deleted_at.is_(None))
                .label("document_count"),
                func.max(ConversationDocument.updated_at).label("last_attachment"),
            )
            .group_by(ConversationDocument.conversation_id)
            .subquery()
        )
        last_activity = func.coalesce(
            doc_counts.c.last_attachment,
            Conversation.updated_at,
            Conversation.created_at,
        ).label("last_activity")
        stmt = (
            select(
                Conversation,
                func.coalesce(doc_counts.c.document_count, literal(0)).label("document_count"),
                last_activity,
            )
            .outerjoin(doc_counts, doc_counts.c.conversation_id == Conversation.id)
            .where(and_(*criteria))
            .order_by(last_activity.desc(), Conversation.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = await self._session.execute(stmt)
        items = [
            _to_conversation_entry(
                conversation=row[0],
                document_count=row.document_count,
                last_activity=row.last_activity,
                default_namespace=self._default_namespace,
            )
            for row in rows
        ]
        count_stmt = select(func.count()).select_from(
            select(Conversation.id).where(and_(*criteria)).subquery()
        )
        total = await self._session.scalar(count_stmt)
        pagination = PaginationWindow(page=page, page_size=page_size, total_count=total or 0)
        return PaginatedResult(items=items, pagination=pagination)

    async def summarize_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> ConversationSummary:
        conversation = await self._session.get(Conversation, _as_uuid(conversation_id))
        if conversation is None:
            raise LookupError("Conversation not found")
        owner_uuid = _as_uuid(owner_user_id)
        if conversation.owner_user_id != owner_uuid:
            raise PermissionError("Conversation does not belong to the user")
        attachment_stmt = (
            select(func.count())
            .select_from(ConversationDocument)
            .where(ConversationDocument.conversation_id == conversation.id)
            .where(ConversationDocument.deleted_at.is_(None))
        )
        attachment_count = await self._session.scalar(attachment_stmt)
        message_stmt = select(
            func.count().label("message_count"),
            func.count().filter(Message.role == "user").label("user_prompts"),
            func.max(Message.created_at).label("last_message"),
        ).where(Message.conversation_id == conversation.id)
        message_row = await self._session.execute(message_stmt)
        result = message_row.one_or_none()
        message_count = int(result.message_count or 0) if result else 0
        user_prompts = int(result.user_prompts or 0) if result else 0
        last_message_at = result.last_message if result else None
        last_activity = (
            max(
                [
                    value
                    for value in (
                        last_message_at,
                        conversation.updated_at,
                        conversation.created_at,
                    )
                    if value is not None
                ]
            )
            if any(
                value is not None
                for value in (last_message_at, conversation.updated_at, conversation.created_at)
            )
            else datetime.now(UTC)
        )
        return ConversationSummary(
            conversation_id=str(conversation.id),
            owner_user_id=str(conversation.owner_user_id) if conversation.owner_user_id else None,
            attachment_count=int(attachment_count or 0),
            message_count=message_count,
            user_prompt_count=user_prompts,
            last_message_at=last_message_at,
            last_activity_at=last_activity,
        )


class DocumentListingService:
    """Lists documents owned by the caller with ingestion metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_documents(
        self,
        *,
        owner_user_id: str,
        page: int,
        page_size: int,
        tags: Sequence[str] | None = None,
        content_hashes: Sequence[str] | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        include_base_documents: bool = False,
    ) -> PaginatedResult:
        owner_uuid = _as_uuid(owner_user_id)
        ownership_clause = Document.owner_user_id == owner_uuid
        if include_base_documents:
            ownership_clause = or_(
                ownership_clause,
                and_(Document.owner_user_id.is_(None), Document.access_scope == "base"),
            )
        criteria = [
            ownership_clause,
            Document.deleted_at.is_(None),
        ]
        normalized_tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
        if normalized_tags:
            criteria.append(Document.tags.contains(normalized_tags))
        normalized_hashes = [h.strip().lower() for h in (content_hashes or []) if h]
        if normalized_hashes:
            criteria.append(Document.content_hash.in_(normalized_hashes))
        if created_after:
            criteria.append(Document.created_at >= created_after)
        if created_before:
            criteria.append(Document.created_at <= created_before)
        stmt = (
            select(Document)
            .where(and_(*criteria))
            .order_by(Document.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        rows = await self._session.execute(stmt)
        items = [_to_document_entry(document=row[0]) for row in rows]
        count_stmt = select(func.count()).select_from(
            select(Document.id).where(and_(*criteria)).subquery()
        )
        total = await self._session.scalar(count_stmt)
        pagination = PaginationWindow(page=page, page_size=page_size, total_count=total or 0)
        return PaginatedResult(items=items, pagination=pagination)


def _to_conversation_entry(
    *,
    conversation: Conversation,
    document_count: int | None,
    last_activity: datetime | None,
    default_namespace: str,
) -> ConversationListEntry:
    metadata = conversation.metadata_ or {}
    namespace = str(metadata.get("namespace") or default_namespace)
    tags = _extract_tags(metadata)
    last_activity_at = last_activity or conversation.updated_at or conversation.created_at
    if last_activity_at is None:
        last_activity_at = datetime.now(UTC)
    return ConversationListEntry(
        conversation_id=str(conversation.id),
        owner_user_id=str(conversation.owner_user_id) if conversation.owner_user_id else None,
        namespace=namespace,
        title=conversation.title,
        country_code=conversation.country_code,
        status=conversation.status,
        tags=tags,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_activity_at=last_activity_at,
        document_count=int(document_count or 0),
    )


def _to_document_entry(*, document: Document) -> DocumentListEntry:
    return DocumentListEntry(
        document_id=str(document.id),
        owner_user_id=str(document.owner_user_id) if document.owner_user_id else None,
        canonical_name=document.canonical_name,
        access_scope=document.access_scope,
        country_code=document.country_code,
        language=document.language,
        tags=list(document.tags or []),
        status=document.status,
        ingestion_stage=document.ingestion_stage,
        ingestion_started_at=document.ingestion_started_at,
        ingestion_completed_at=document.ingestion_completed_at,
        content_hash=document.content_hash,
        created_at=document.created_at,
        updated_at=document.updated_at,
        metadata=document.metadata_ or None,
    )


def _normalize_tags(tags: Sequence[str] | None) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    for tag in tags:
        if not tag:
            continue
        cleaned = tag.strip().lower()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _extract_tags(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("tags") if isinstance(metadata, dict) else None
    if not isinstance(raw, list):
        return []
    tags: list[str] = []
    for value in raw:
        if isinstance(value, str) and value:
            tags.append(value)
    return tags


def _as_uuid(value: str) -> UUID:
    return UUID(str(value))


__all__ = [
    "ConversationListEntry",
    "ConversationListingService",
    "ConversationSummary",
    "DocumentListEntry",
    "DocumentListingService",
    "PaginatedResult",
    "PaginationWindow",
]
