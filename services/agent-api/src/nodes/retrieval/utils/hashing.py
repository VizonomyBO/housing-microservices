"""Hash helpers shared by retrieval nodes."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable


def compute_scope_hash(entries: Iterable[str]) -> str:
    """Compute a deterministic hash for the attachment scope."""

    normalized = sorted(str(entry) for entry in entries if entry)
    joined = "|".join(normalized)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return digest
