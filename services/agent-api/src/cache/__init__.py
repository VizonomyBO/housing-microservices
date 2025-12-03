"""Cache utilities for the agent-api service.

The cache package re-exports several helpers for convenience, but importing all of
them eagerly creates circular dependencies (CacheWriter imports AgentState, which
in turn touches cache.response_serializer). To keep import order predictable we
only load the heavier modules on demand via ``__getattr__``.
"""

from importlib import import_module

from .cache_keys import RetrievalCacheKeyInputs, build_retrieval_cache_key
from .response_serializer import (
    CacheCitation,
    CacheResponsePayload,
    CacheWorkflowPlanExcerpt,
    deserialize_cache_response,
    serialize_cache_response,
)
from .valkey_async_client import ValkeyAsyncClient
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
    "ValkeyAsyncClient",
    "ValkeyCacheClientProtocol",
    "build_retrieval_cache_key",
    "deserialize_cache_response",
    "maybe_serve_from_cache",
    "serialize_cache_response",
]

_LAZY_ATTRS = {
    "CacheWriter": (".cache_writer", "CacheWriter"),
    "CacheWriteResult": (".cache_writer", "CacheWriteResult"),
    "CacheShortCircuitResult": (".cache_writer", "CacheShortCircuitResult"),
    "maybe_serve_from_cache": (".cache_writer", "maybe_serve_from_cache"),
}


def __getattr__(name: str):
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(f"{__name__}{module_name}")
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
