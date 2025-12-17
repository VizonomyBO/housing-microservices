from __future__ import annotations

import os
from uuid import UUID

DEFAULT_VOYAGE_EMBEDDING_DIMENSION = 1024
SYSTEM_OWNER_SENTINEL = UUID("00000000-0000-0000-0000-000000000000")


def resolve_embedding_dimension() -> int:
    """
    Resolve the embedding dimension for voyage-context-3 vectors.
    Falls back to 1024 when not explicitly configured.
    """
    raw_value = (
        os.getenv("VOYAGE_EMBEDDING_DIM")
        or os.getenv("VOYAGE_OUTPUT_DIMENSION")
        or os.getenv("EMBEDDING_DIMENSION")
        or str(DEFAULT_VOYAGE_EMBEDDING_DIMENSION)
    )
    try:
        dimension = int(raw_value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"Invalid embedding dimension: {raw_value!r}. "
            "Set VOYAGE_EMBEDDING_DIM/VOYAGE_OUTPUT_DIMENSION to a positive integer."
        ) from exc

    if dimension <= 0:
        raise ValueError(
            f"Embedding dimension must be positive, got {dimension}. "
            "Set VOYAGE_EMBEDDING_DIM/VOYAGE_OUTPUT_DIMENSION to a positive integer."
        )
    return dimension


EMBEDDING_DIMENSION = resolve_embedding_dimension()
