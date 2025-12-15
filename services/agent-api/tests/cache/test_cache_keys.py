from __future__ import annotations

import hashlib

from cache.cache_keys import RetrievalCacheKeyInputs, build_retrieval_cache_key


def test_build_retrieval_cache_key_normalizes_components() -> None:
    inputs = RetrievalCacheKeyInputs(
        conversation_id="Conv-123",
        intent="Route:Informational",
        workflow_version="V1",
        document_hashes=[" AAAA ", "bbbb", "AAAA"],
    )

    cache_key = build_retrieval_cache_key(inputs)

    expected_digest = hashlib.sha256(b"aaaa|bbbb").hexdigest()
    assert (
        cache_key == f"agent-api:retrieval:conv-123:route-informational:v1:docs-{expected_digest}"
    )


def test_build_retrieval_cache_key_handles_missing_values() -> None:
    inputs = RetrievalCacheKeyInputs(conversation_id="  ")

    cache_key = build_retrieval_cache_key(inputs)

    assert cache_key.startswith("agent-api:retrieval:conversation:intent:workflow:")
    assert cache_key.endswith("docs-none")
