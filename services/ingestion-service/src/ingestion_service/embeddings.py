from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(slots=True)
class VoyageEmbeddingClient(VoyageEmbeddingClientProtocol):
    """Thin wrapper around langchain-voyageai embeddings."""

    api_key: str
    model: str
    output_dimension: int | None = None

    async def embed(
        self,
        texts: Sequence[str],
        *,
        output_dimension: int,
        input_type: str = "document",
    ) -> list[list[float]]:
        if not texts:
            return []

        # Set API key in environment for VoyageAIEmbeddings
        os.environ["VOYAGE_API_KEY"] = self.api_key

        # Cast output_dimension to the expected Literal type
        dim = output_dimension or self.output_dimension
        valid_dims = (256, 512, 1024, 2048)
        if dim not in valid_dims:
            raise ValueError(f"output_dimension must be one of {valid_dims}, got {dim}")

        # Type-safe cast to Literal type
        typed_dim = cast(Literal[256, 512, 1024, 2048], dim)

        client = VoyageAIEmbeddings(
            model=self.model,
            output_dimension=typed_dim,
            truncation=True,
        )
        return await asyncio.to_thread(client.embed_documents, list(texts))
