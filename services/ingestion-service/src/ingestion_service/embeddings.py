from __future__ import annotations

import logging
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

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
        client = VoyageAIEmbeddings(
            model=self.model,
            api_key=self.api_key,
            output_dimension=output_dimension or self.output_dimension,
            truncation=True,
        )
        return await asyncio.to_thread(client.embed_documents, list(texts))
