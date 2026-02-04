from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from langchain_voyageai import VoyageAIEmbeddings

logger = logging.getLogger(__name__)


class VoyageEmbeddingClientProtocol(Protocol):
    """Protocol for embedding clients used by ingestion."""

    async def embed(
        self,
        texts: Sequence[str],
        *,
        output_dimension: int,
        input_type: str = "document",
    ) -> list[list[float]]: ...


@dataclass
class VoyageEmbeddingClient(VoyageEmbeddingClientProtocol):
    """Thin wrapper around langchain-voyageai embeddings.

    Caches VoyageAIEmbeddings clients by output_dimension to prevent memory leaks
    from creating new clients on every embed() call. Each client holds HTTP
    connection pools and internal caches that accumulate if not reused.
    """

    api_key: str
    model: str
    output_dimension: int | None = None
    _clients: dict[int, VoyageAIEmbeddings] = field(default_factory=dict, init=False, repr=False)

    def _get_client(self, dim: int) -> VoyageAIEmbeddings:
        """Get or create a cached VoyageAIEmbeddings client for the given dimension."""
        if dim not in self._clients:
            os.environ["VOYAGE_API_KEY"] = self.api_key
            typed_dim = cast(Literal[256, 512, 1024, 2048], dim)
            self._clients[dim] = VoyageAIEmbeddings(
                model=self.model,
                output_dimension=typed_dim,
                truncation=True,
            )
            logger.debug("Created VoyageAIEmbeddings client for dimension %d", dim)
        return self._clients[dim]

    async def embed(
        self,
        texts: Sequence[str],
        *,
        output_dimension: int,
        input_type: str = "document",
    ) -> list[list[float]]:
        if not texts:
            return []

        dim = output_dimension or self.output_dimension
        valid_dims = (256, 512, 1024, 2048)
        if dim not in valid_dims:
            raise ValueError(f"output_dimension must be one of {valid_dims}, got {dim}")

        client = self._get_client(dim)
        return await asyncio.to_thread(client.embed_documents, list(texts))
