from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from voyageai import AsyncClient as VoyageAsyncClient
from voyageai import error as voyage_errors

logger = logging.getLogger(__name__)


class VoyageEmbeddingClientProtocol(Protocol):
    """Protocol for embedding clients used by ingestion."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(slots=True)
class VoyageEmbeddingClient(VoyageEmbeddingClientProtocol):
    """Thin wrapper around voyageai.AsyncClient with retries."""

    api_key: str
    model: str
    timeout_seconds: float = 30.0
    max_batch: int = 64

    def __post_init__(self) -> None:
        self._client = VoyageAsyncClient(api_key=self.api_key, timeout=self.timeout_seconds)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.max_batch):
            batch = list(texts[start : start + self.max_batch])
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
                retry=retry_if_exception_type(
                    (voyage_errors.APIError, voyage_errors.APIConnectionError)
                ),
            ):
                with attempt:
                    response = await self._client.embed(batch, model=self.model)
                    vectors = [list(map(float, embedding)) for embedding in response.embeddings]
                    embeddings.extend(vectors)
        return embeddings

