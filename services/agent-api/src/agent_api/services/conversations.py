"""Conversation lifecycle helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from shared_data_layer.db.models.conversations import Conversation, Message
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def ensure_conversation(
        self,
        *,
        owner_user_id: str | None,
        country_code: str | None,
        title: str | None,
        namespace: str | None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Conversation:
        namespace = (namespace or "default").strip() or "default"
        metadata_payload = dict(metadata or {})
        if tags:
            metadata_payload["tags"] = tags
        metadata_payload.setdefault("namespace", namespace)

        record = Conversation(
            id=uuid4(),
            owner_user_id=_coerce_uuid(owner_user_id, allow_none=True),
            country_code=country_code.strip().upper() if country_code else None,
            status="active",
            title=(title or "").strip() or None,
            metadata_=metadata_payload or None,
            document_scope=None,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        logger.info(
            "conversation.created",
            extra={"conversation_id": str(record.id), "owner_user_id": owner_user_id},
        )
        return record

    async def fetch_conversation(
        self, conversation_id: str, *, owner_user_id: str | None
    ) -> Conversation:
        conversation = await self._session.get(Conversation, _coerce_uuid(conversation_id))
        if conversation is None:
            raise LookupError("Conversation not found")
        if (
            conversation.owner_user_id
            and owner_user_id
            and str(conversation.owner_user_id) != owner_user_id
        ):
            raise PermissionError("Conversation not found")
        return conversation

    async def list_conversations(
        self,
        *,
        owner_user_id: str,
        page: int,
        page_size: int,
        tags: list[str],
        country_code: str | None,
    ) -> tuple[list[Conversation], int]:
        query = select(Conversation).where(
            Conversation.owner_user_id == _coerce_uuid(owner_user_id, allow_none=True),
            Conversation.status == "active",
        )
        if country_code:
            query = query.where(Conversation.country_code == country_code.upper())
        total_count = (
            await self._session.execute(query.with_only_columns(func.count()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    query.order_by(Conversation.created_at.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                )
            )
            .scalars()
            .all()
        )
        if tags:
            filtered = []
            for row in rows:
                row_tags = (row.metadata_ or {}).get("tags") or []
                if all(tag in row_tags for tag in tags):
                    filtered.append(row)
            rows = list(filtered)
            total_count = len(rows)
        return list(rows), int(total_count)

    async def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        convo_uuid = _coerce_uuid(conversation_id)
        ordinal_query = select(func.coalesce(func.max(Message.ordinal), -1) + 1).where(
            Message.conversation_id == convo_uuid
        )
        next_ordinal = (await self._session.execute(ordinal_query)).scalar_one()
        message = Message(
            id=uuid4(),
            conversation_id=convo_uuid,
            role=role,
            content=content,
            ordinal=int(next_ordinal),
            status="final",
            metadata_=metadata,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def list_messages(
        self,
        *,
        conversation_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[Message], str | None, int]:
        convo_uuid = _coerce_uuid(conversation_id)
        stmt = select(Message).where(Message.conversation_id == convo_uuid)
        if cursor:
            stmt = stmt.where(
                and_(
                    Message.created_at > _decode_cursor_timestamp(cursor),
                )
            )
        stmt = stmt.order_by(
            Message.created_at.asc(), Message.ordinal.asc(), Message.id.asc()
        ).limit(limit + 1)
        rows = (await self._session.execute(stmt)).scalars().all()
        page = list(rows[:limit])
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = _encode_cursor_timestamp(last.created_at)
        remaining = 0
        if page and next_cursor:
            remaining_stmt = (
                select(func.count())
                .where(Message.conversation_id == convo_uuid)
                .where(Message.created_at > _decode_cursor_timestamp(next_cursor))
            )
            remaining = (await self._session.execute(remaining_stmt)).scalar_one()
        return page, next_cursor, int(remaining)


def _coerce_uuid(value: str | UUID | None, *, allow_none: bool = False) -> UUID | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError("UUID value is required")
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _encode_cursor_timestamp(dt: datetime) -> str:
    return dt.replace(tzinfo=UTC).isoformat()


def _decode_cursor_timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


__all__ = ["ConversationService"]
