"""Cache utilities for the agent-api service."""

from .cache_keys import RetrievalCacheKeyInputs, build_retrieval_cache_key
from .cache_writer import (
    CacheShortCircuitResult,
    CacheWriter,
    CacheWriteResult,
    maybe_serve_from_cache,
)
from .response_serializer import (
    CacheCitation,
    CacheResponsePayload,
    CacheWorkflowPlanExcerpt,
    deserialize_cache_response,
    serialize_cache_response,
)
from .valkey_client import InMemoryValkeyClient, ValkeyCacheClientProtocol

__all__ = [
    "CacheCitation",
    "CacheResponsePayload",
    "CacheShortCircuitResult",
    "CacheWorkflowPlanExcerpt",
    "CacheWriteResult",
    "CacheWriter",
    "InMemoryValkeyClient",
    "RetrievalCacheKeyInputs",
    "ValkeyCacheClientProtocol",
    "build_retrieval_cache_key",
    "deserialize_cache_response",
    "maybe_serve_from_cache",
    "serialize_cache_response",
]
