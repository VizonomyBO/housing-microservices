"""Cache key helpers for retrieval workflows."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

_COMPONENT_SANITIZER = re.compile(r"[^a-z0-9]+")


def _normalize_component(value: str | None, *, fallback: str) -> str:
    if not value:
        return fallback
    normalized = _COMPONENT_SANITIZER.sub("-", value.strip().lower())
    normalized = normalized.strip("-")
    return normalized or fallback


def _normalize_document_hash(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _document_fingerprint(document_hashes: Iterable[str | None]) -> str:
    normalized_hashes = sorted(
        {
            hash_value
            for hash_value in (
                _normalize_document_hash(hash_value) for hash_value in document_hashes
            )
            if hash_value
        }
    )
    if not normalized_hashes:
        return "docs-none"
    digest_source = "|".join(normalized_hashes)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return f"docs-{digest}"


@dataclass(slots=True)
class RetrievalCacheKeyInputs:
    """Structured payload describing the retrieval cache namespace."""

    conversation_id: str
    intent: str | None = None
    workflow_version: str | None = None
    document_hashes: Iterable[str | None] = field(default_factory=tuple)
    namespace: str = "agent-api:retrieval"


def build_retrieval_cache_key(inputs: RetrievalCacheKeyInputs) -> str:
    """Build a deterministic cache key for retrieval + workflow planning results."""

    conversation_component = _normalize_component(inputs.conversation_id, fallback="conversation")
    intent_component = _normalize_component(inputs.intent, fallback="intent")
    version_component = _normalize_component(inputs.workflow_version, fallback="workflow")
    docs_component = _document_fingerprint(inputs.document_hashes)
    namespace = inputs.namespace.strip().lower() or "agent-api:retrieval"
    return f"{namespace}:{conversation_component}:{intent_component}:{version_component}:{docs_component}"


__all__ = ["RetrievalCacheKeyInputs", "build_retrieval_cache_key"]
