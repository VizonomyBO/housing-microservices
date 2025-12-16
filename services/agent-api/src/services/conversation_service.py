"""Conversation lifecycle helpers for HTTP endpoints and workflows."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from shared_data_layer.db.models.conversations import Conversation
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class ConversationRecord:
    """Serializable conversation projection."""

    conversation_id: str
    owner_user_id: str | None
    namespace: str
    title: str | None
    country_code: str | None
    status: str
    tags: list[str]
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(slots=True)
class ConversationEnsureResult:
    """Return value for idempotent ensure calls."""

    conversation: ConversationRecord
    created: bool


DEFAULT_CONVERSATION_NAMESPACE = "reduced-e2e"
DEFAULT_CONVERSATION_TITLE = "Reduced E2E Smoke Session"


class ConversationService:
    """Encapsulates deterministic conversation creation + lookups."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        default_namespace: str = DEFAULT_CONVERSATION_NAMESPACE,
        default_title: str = DEFAULT_CONVERSATION_TITLE,
    ) -> None:
        self._session = session
        self._default_namespace = _normalize_namespace(default_namespace)
        self._default_title = default_title

    async def ensure_conversation(
        self,
        *,
        owner_user_id: str,
        country_code: str | None = None,
        title: str | None = None,
        namespace: str | None = None,
        tags: Sequence[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationEnsureResult:
        owner_uuid = _as_uuid(owner_user_id)
        namespace_slug = _normalize_namespace(namespace) or self._default_namespace
        conversation_id = deterministic_conversation_id(
            owner_user_id=str(owner_uuid),
            namespace=namespace_slug,
            default_namespace=self._default_namespace,
        )
        conversation = await self._session.get(Conversation, UUID(conversation_id))
        created = conversation is None
        normalized_country = _normalize_country_code(country_code)
        desired_title = _normalize_title(title) or (
            self._default_title if namespace_slug == self._default_namespace else None
        )
        requested_tags = _unique_tags(tags)

        if conversation is None:
            payload_meta = _merge_metadata(
                base_metadata=metadata,
                namespace=namespace_slug,
                tags=requested_tags,
            )
            conversation = Conversation(
                id=UUID(conversation_id),
                owner_user_id=owner_uuid,
                country_code=normalized_country,
                status="active",
                title=desired_title,
                metadata_=payload_meta,
            )
            self._session.add(conversation)
        else:
            if normalized_country and not conversation.country_code:
                conversation.country_code = normalized_country
            if desired_title and not conversation.title:
                conversation.title = desired_title
            merged_meta = _merge_metadata(
                base_metadata=conversation.metadata_,
                namespace=namespace_slug,
                tags=requested_tags,
            )
            if metadata:
                merged_meta.update(metadata)
            conversation.metadata_ = merged_meta

        await self._session.flush()
        await self._session.refresh(conversation)
        record = self._to_record(conversation)
        return ConversationEnsureResult(conversation=record, created=created)

    async def fetch_conversation(
        self,
        conversation_id: str,
        *,
        owner_user_id: str | None = None,
    ) -> ConversationRecord:
        conversation = await self._session.get(Conversation, _as_uuid(conversation_id))
        if conversation is None:
            raise LookupError("Conversation not found")
        if (
            owner_user_id is not None
            and conversation.owner_user_id is not None
            and conversation.owner_user_id != _as_uuid(owner_user_id)
        ):
            raise PermissionError("Conversation does not belong to the user")
        return self._to_record(conversation)

    def _to_record(self, conversation: Conversation) -> ConversationRecord:
        metadata = conversation.metadata_ or {}
        tags = _extract_tags(metadata)
        namespace = str(metadata.get("namespace") or self._default_namespace)
        owner = str(conversation.owner_user_id) if conversation.owner_user_id else None
        return ConversationRecord(
            conversation_id=str(conversation.id),
            owner_user_id=owner,
            namespace=namespace,
            title=conversation.title,
            country_code=conversation.country_code,
            status=conversation.status,
            tags=tags,
            metadata=metadata,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


def deterministic_conversation_id(
    owner_user_id: str,
    *,
    namespace: str | None = None,
    default_namespace: str = DEFAULT_CONVERSATION_NAMESPACE,
) -> str:
    """Derive the deterministic UUID used by ConversationService.ensure_conversation."""

    owner_uuid = _as_uuid(owner_user_id)
    namespace_slug = _normalize_namespace(namespace) or _normalize_namespace(default_namespace)
    if not namespace_slug:
        raise ValueError("namespace must resolve to a non-empty slug")
    return str(uuid5(NAMESPACE_URL, f"{namespace_slug}-{owner_uuid}"))


def _as_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError("owner_user_id must be a valid UUID") from exc


def _normalize_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None
    code = country_code.strip().upper()
    if len(code) != 3:
        raise ValueError("country_code must be a 3-letter ISO code")
    return code


def _normalize_namespace(namespace: str | None) -> str:
    if namespace is None:
        return ""
    slug = namespace.strip().lower()
    if not slug:
        return ""
    slug = re.sub(r"[^a-z0-9-_]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        return ""
    return slug[:64]


def _normalize_title(title: str | None) -> str | None:
    if title is None:
        return None
    trimmed = title.strip()
    return trimmed or None


def _unique_tags(tags: Sequence[str] | None) -> list[str]:
    if not tags:
        return []
    seen: dict[str, None] = {}
    for tag in tags:
        if not tag:
            continue
        normalized = tag.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if lower in seen:
            continue
        seen[lower] = None
    return list(seen.keys())


def _extract_tags(metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("tags") if isinstance(metadata, dict) else None
    if not isinstance(raw, Iterable):
        return []
    tags: list[str] = []
    for value in raw:
        if isinstance(value, str) and value:
            tags.append(value)
    return tags


def _merge_metadata(
    *,
    base_metadata: dict[str, Any] | None,
    namespace: str,
    tags: Sequence[str],
) -> dict[str, Any]:
    metadata = dict(base_metadata or {})
    metadata.setdefault("namespace", namespace)
    if tags:
        existing = metadata.get("tags")
        combined = list(existing or [])
        for tag in tags:
            if tag not in combined:
                combined.append(tag)
        metadata["tags"] = combined
    return metadata


__all__ = [
    "ConversationEnsureResult",
    "ConversationRecord",
    "ConversationService",
]
