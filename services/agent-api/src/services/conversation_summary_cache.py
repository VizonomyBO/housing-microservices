"""Lightweight cache for conversation transcript summaries."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime

from cache.valkey_client import ValkeyCacheClientProtocol

from .listing_service import ConversationSummary

logger = logging.getLogger(__name__)


class ConversationSummaryCache:
    """Caches conversation summary projections to avoid repetitive DB scans."""

    def __init__(
        self,
        client: ValkeyCacheClientProtocol,
        *,
        prefix: str = "conversation:summary",
        ttl_seconds: int = 300,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    async def get(self, conversation_id: str) -> ConversationSummary | None:
        key = self._key(conversation_id)
        try:
            raw = await self._client.get(key)
        except Exception as exc:  # pragma: no cover - defensive guardrails
            logger.debug("Summary cache read failed for %s: %s", key, exc)
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(
                raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
            )
            return _summary_from_payload(payload)
        except Exception as exc:  # pragma: no cover - defensive guardrails
            logger.debug("Summary cache decode failed for %s: %s", key, exc)
            return None

    async def set(self, summary: ConversationSummary) -> None:
        key = self._key(summary.conversation_id)
        payload = asdict(summary)
        if summary.last_message_at:
            payload["last_message_at"] = summary.last_message_at.replace(tzinfo=UTC).isoformat()
        if summary.last_activity_at:
            payload["last_activity_at"] = summary.last_activity_at.replace(tzinfo=UTC).isoformat()
        try:
            await self._client.set(key, json.dumps(payload), ttl_seconds=self._ttl_seconds)
        except Exception as exc:  # pragma: no cover - defensive guardrails
            logger.debug("Summary cache write failed for %s: %s", key, exc)

    async def invalidate(self, conversation_id: str) -> None:
        key = self._key(conversation_id)
        try:
            await self._client.delete(key)
        except Exception as exc:  # pragma: no cover - defensive guardrails
            logger.debug("Summary cache invalidate failed for %s: %s", key, exc)

    def _key(self, conversation_id: str) -> str:
        return f"{self._prefix}:{conversation_id}"


def _summary_from_payload(payload: dict) -> ConversationSummary:
    last_message_at = _parse_datetime(payload.get("last_message_at"))
    last_activity_at = _parse_datetime(payload.get("last_activity_at")) or datetime.now(UTC)
    return ConversationSummary(
        conversation_id=str(payload.get("conversation_id")),
        owner_user_id=str(payload["owner_user_id"]) if payload.get("owner_user_id") else None,
        attachment_count=int(payload.get("attachment_count", 0) or 0),
        message_count=int(payload.get("message_count", 0) or 0),
        user_prompt_count=int(payload.get("user_prompt_count", 0) or 0),
        last_message_at=last_message_at,
        last_activity_at=last_activity_at,
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:  # pragma: no cover - defensive guardrails
        return None


__all__ = ["ConversationSummaryCache"]
