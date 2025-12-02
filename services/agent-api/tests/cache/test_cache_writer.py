from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from cache import (
    CacheCitation,
    CacheResponsePayload,
    CacheWriter,
    InMemoryValkeyClient,
    deserialize_cache_response,
    maybe_serve_from_cache,
    serialize_cache_response,
)
from state.agent_state import CacheMetadata


def _fixed_now() -> datetime:
    return datetime(2025, 1, 1, 12, 0, tzinfo=UTC)


def test_serialize_cache_response_orders_payload() -> None:
    payload = CacheResponsePayload(
        answer_text="final",
        citations=[
            CacheCitation(doc_id="doc-b", chunk_id="chunk-2", snippet="b"),
            CacheCitation(doc_id="doc-a", chunk_id="chunk-3", snippet="a"),
        ],
        chunk_ids=["chunk-3", "chunk-1", "chunk-1"],
        model_metadata={"temperature": 0.2, "model": "gpt-5-mini"},
    )

    serialized = serialize_cache_response(payload)
    decoded = json.loads(serialized.decode("utf-8"))

    assert decoded["chunk_ids"] == ["chunk-1", "chunk-3"]
    assert [citation["doc_id"] for citation in decoded["citations"]] == [
        "doc-a",
        "doc-b",
    ]


@pytest.mark.asyncio
async def test_cache_writer_persists_payload_and_updates_metadata() -> None:
    client = InMemoryValkeyClient()
    writer = CacheWriter(client=client, clock=_fixed_now)
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv:route:v1:docs")
    payload = CacheResponsePayload(answer_text="cached", chunk_ids=["chunk-1"])

    result = await writer.write(payload=payload, cache_metadata=metadata)

    assert result.succeeded is True
    assert result.cache_metadata.written_at == _fixed_now()
    assert metadata.cache_key is not None
    stored = await client.get(metadata.cache_key)
    assert stored is not None
    hydrated = deserialize_cache_response(stored)
    assert hydrated.answer_text == "cached"


@pytest.mark.asyncio
async def test_cache_writer_skips_when_key_missing() -> None:
    client = InMemoryValkeyClient()
    writer = CacheWriter(client=client, clock=_fixed_now)
    metadata = CacheMetadata(cache_key=None)
    payload = CacheResponsePayload(answer_text="noop")

    result = await writer.write(payload=payload, cache_metadata=metadata)

    assert result.succeeded is False
    assert await client.get("some-key") is None


class FailingClient(InMemoryValkeyClient):
    async def set(self, key: str, value: bytes | str, *, ttl_seconds: int | None = None) -> None:  # type: ignore[override]
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_cache_writer_handles_client_errors() -> None:
    client = FailingClient()
    writer = CacheWriter(client=client, clock=_fixed_now)
    metadata = CacheMetadata(cache_key="agent-api:retrieval:oops")
    payload = CacheResponsePayload(answer_text="err")

    result = await writer.write(payload=payload, cache_metadata=metadata)

    assert result.succeeded is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_maybe_serve_from_cache_returns_payload_on_hit() -> None:
    client = InMemoryValkeyClient()
    writer = CacheWriter(client=client, clock=_fixed_now)
    metadata = CacheMetadata(cache_key="agent-api:retrieval:conv:foo")
    payload = CacheResponsePayload(answer_text="from-cache", chunk_ids=["chunk-9"])
    await writer.write(payload=payload, cache_metadata=metadata)

    result = await maybe_serve_from_cache(client=client, cache_metadata=metadata, clock=_fixed_now)

    assert result.hit is True
    assert result.payload is not None
    assert result.payload.answer_text == "from-cache"
    assert result.cache_metadata.hit is True
    assert result.cache_metadata.hit_at == _fixed_now()


@pytest.mark.asyncio
async def test_maybe_serve_from_cache_tags_miss_when_missing() -> None:
    client = InMemoryValkeyClient()
    metadata = CacheMetadata(cache_key="agent-api:retrieval:missing")

    result = await maybe_serve_from_cache(client=client, cache_metadata=metadata)

    assert result.hit is False
    assert metadata.cache_key is not None
    assert client.telemetry[-1] == {
        "event": "miss",
        "key": metadata.cache_key,
        "reason": "not_found",
    }
