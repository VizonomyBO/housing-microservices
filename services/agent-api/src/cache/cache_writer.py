"""CacheWriter + helpers for interacting with Valkey."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cache.response_serializer import (
    CacheResponsePayload,
    deserialize_cache_response,
    serialize_cache_response,
)
from cache.valkey_client import ValkeyCacheClientProtocol
from state.agent_state import AgentState, CacheMetadata

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from telemetry.cache_observability import CacheObservability

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CacheWriteResult:
    """Result metadata from CacheWriter.write."""

    cache_metadata: CacheMetadata
    cache_key: str | None
    bytes_written: bytes | None
    error: Exception | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.cache_key is not None


@dataclass(slots=True)
class CacheWriter:
    """Write-through cache helper for LangGraph responses."""

    client: ValkeyCacheClientProtocol
    default_ttl_seconds: int = 60 * 60 * 48
    serializer: Callable[[CacheResponsePayload], bytes] = field(default=serialize_cache_response)
    clock: Clock = field(default=_utc_now)
    observability: CacheObservability | None = None
    disable_writes: bool = False

    async def write(
        self,
        *,
        payload: CacheResponsePayload,
        cache_metadata: CacheMetadata,
        cache_key: str | None = None,
        ttl_seconds: int | None = None,
        state: AgentState | None = None,
        db_session: AsyncSession | None = None,
    ) -> CacheWriteResult:
        """Serialize + persist payload if cache metadata includes a key.

        Returns the updated cache metadata (written_at timestamp) regardless of whether
        the write succeeded. Exceptions are logged and swallowed per Task 07 guidance.
        """

        key = cache_key or cache_metadata.cache_key
        if not key:
            logger.debug("CacheWriter skipped write because cache_key is missing")
            return CacheWriteResult(
                cache_metadata=cache_metadata, cache_key=None, bytes_written=None
            )

        serialized = self.serializer(payload)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        if self.disable_writes:
            logger.info(
                "CacheWriter running in reduced-scope mode; skipping Valkey write for %s",
                key,
            )
        else:
            try:
                await self.client.set(key, serialized, ttl_seconds=ttl)
                await self.client.tag_miss(key, reason="write_through")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("CacheWriter failed to persist key %s: %s", key, exc)
                return CacheWriteResult(
                    cache_metadata=cache_metadata,
                    cache_key=key,
                    bytes_written=None,
                    error=exc,
                )

        updated_metadata = cache_metadata.model_copy(
            update={"cache_key": key, "written_at": self.clock(), "hit": False}
        )
        result = CacheWriteResult(
            cache_metadata=updated_metadata,
            cache_key=key,
            bytes_written=None if self.disable_writes else serialized,
        )
        if self.observability is not None:
            resolved_route = state.route.value if state and state.route else None
            await self.observability.record_cache_write(
                cache_key=key,
                route=resolved_route,
                ttl_seconds=ttl,
                session=db_session,
                state=state,
                payload=payload,
            )
        return result


@dataclass(slots=True)
class CacheShortCircuitResult:
    """Return value from maybe_serve_from_cache."""

    cache_metadata: CacheMetadata
    hit: bool
    payload: CacheResponsePayload | None
    cache_key: str | None


async def maybe_serve_from_cache(
    *,
    client: ValkeyCacheClientProtocol,
    cache_metadata: CacheMetadata,
    cache_key: str | None = None,
    clock: Clock = _utc_now,
    observability: CacheObservability | None = None,
    state: AgentState | None = None,
) -> CacheShortCircuitResult:
    """Attempt to pull a cached response, tagging telemetry hooks on hit/miss."""

    key = cache_key or cache_metadata.cache_key
    if not key:
        logger.debug("Cache short-circuit skipped because cache_key missing")
        return CacheShortCircuitResult(
            cache_metadata=cache_metadata,
            hit=False,
            payload=None,
            cache_key=None,
        )

    latency_ms: float | None = None
    try:
        start = clock()
        raw_value = await client.get(key)
        latency_ms = (clock() - start).total_seconds() * 1000
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Cache read failed for %s: %s", key, exc)
        return CacheShortCircuitResult(
            cache_metadata=cache_metadata, hit=False, payload=None, cache_key=key
        )

    if raw_value is None:
        try:
            await client.tag_miss(key, reason="not_found")
        except Exception:  # pragma: no cover - telemetry best-effort
            logger.debug("Cache miss telemetry failed for %s", key)
        if observability is not None:
            resolved_route = state.route.value if state and state.route else None
            await observability.record_cache_miss(
                cache_key=key,
                route=resolved_route,
                reason="not_found",
                latency_ms=latency_ms,
            )
        return CacheShortCircuitResult(
            cache_metadata=cache_metadata, hit=False, payload=None, cache_key=key
        )

    try:
        payload = deserialize_cache_response(raw_value)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to deserialize cache payload for %s: %s", key, exc)
        return CacheShortCircuitResult(
            cache_metadata=cache_metadata, hit=False, payload=None, cache_key=key
        )

    updated_metadata = cache_metadata.model_copy(
        update={"cache_key": key, "hit": True, "hit_at": clock()}
    )

    try:
        await client.tag_hit(key)
    except Exception:  # pragma: no cover
        logger.debug("Cache hit telemetry failed for %s", key)

    if observability is not None:
        resolved_route = state.route.value if state and state.route else None
        await observability.record_cache_hit(
            cache_key=key,
            route=resolved_route,
            latency_ms=latency_ms,
        )

    return CacheShortCircuitResult(
        cache_metadata=updated_metadata,
        hit=True,
        payload=payload,
        cache_key=key,
    )


__all__ = [
    "CacheShortCircuitResult",
    "CacheWriteResult",
    "CacheWriter",
    "maybe_serve_from_cache",
]
