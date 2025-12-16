"""External model client wrappers (OpenAI, Voyage)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI, OpenAIError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from voyageai import AsyncClient as VoyageAsyncClient
from voyageai import error as voyage_errors

logger = logging.getLogger(__name__)


class VoyageEmbeddingClientProtocol(Protocol):
    """Protocol for embedding clients used by ingestion + retrieval."""

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class VoyageRerankClientProtocol(Protocol):
    """Protocol for rerank clients used during retrieval fusion."""

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[float]: ...


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


@dataclass(slots=True)
class VoyageRerankClient(VoyageRerankClientProtocol):
    """Thin wrapper around voyageai.AsyncClient.rerank with retries."""

    api_key: str
    model: str
    timeout_seconds: float = 30.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        self._client = VoyageAsyncClient(api_key=self.api_key, timeout=self.timeout_seconds)

    async def rerank(
        self, query: str, documents: Sequence[str], *, top_k: int | None = None
    ) -> list[float]:
        if not query or not documents:
            return []
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type(
                (voyage_errors.APIError, voyage_errors.APIConnectionError)
            ),
        ):
            with attempt:
                response = await self._client.rerank(
                    query=query,
                    documents=list(documents),
                    model=self.model,
                    top_k=top_k,
                )
                scores = [0.0 for _ in documents]
                results = getattr(response, "results", None) or getattr(response, "data", None)
                if not results:
                    return scores
                for item in results:
                    index = getattr(item, "index", None)
                    if index is None and isinstance(item, dict):
                        index = item.get("index")
                    if index is None or not 0 <= int(index) < len(scores):
                        continue
                    score = getattr(item, "relevance_score", None)
                    if score is None and isinstance(item, dict):
                        score = item.get("relevance_score")
                    scores[int(index)] = float(score or 0.0)
                return scores
        raise RuntimeError("Voyage rerank failed after retries")


class OpenAIChatClientProtocol(Protocol):
    """Protocol for chat completion clients."""

    async def complete(
        self, messages: Sequence[dict[str, str]], *, temperature: float, max_tokens: int
    ) -> str: ...


@dataclass(slots=True)
class OpenAIChatClient(OpenAIChatClientProtocol):
    """Async Chat Completions client with retry/backoff."""

    api_key: str
    model: str
    timeout_seconds: float = 30.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        self._client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_seconds)

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type(OpenAIError),
        ):
            with attempt:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=list(messages),
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                )
                choice = response.choices[0]
                content = choice.message.content or ""
                return content.strip()
        raise RuntimeError("OpenAI completion failed after retries")


__all__ = [
    "OpenAIChatClient",
    "OpenAIChatClientProtocol",
    "VoyageEmbeddingClient",
    "VoyageEmbeddingClientProtocol",
    "VoyageRerankClient",
    "VoyageRerankClientProtocol",
]
