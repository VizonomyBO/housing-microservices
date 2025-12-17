"""LLM and embedding client adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI
from voyageai import Client as VoyageClient


class OpenAIChatClient:
    def __init__(self, *, api_key: str, model: str):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=False,
            **kwargs,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        return content


class VoyageEmbeddingClient:
    def __init__(self, *, api_key: str, model: str):
        self._client = VoyageClient(api_key=api_key)
        self._model = model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        response = self._client.embed(texts=list(texts), model=self._model)
        return response.embeddings  # type: ignore[attr-defined]


class VoyageRerankClient:
    def __init__(self, *, api_key: str, model: str):
        self._client = VoyageClient(api_key=api_key)
        self._model = model

    async def rerank(self, query: str, documents: Sequence[str], top_k: int) -> list[float]:
        return await asyncio.to_thread(self._rerank_sync, query, documents, top_k)

    def _rerank_sync(self, query: str, documents: Sequence[str], top_k: int) -> list[float]:
        response = self._client.rerank(
            query=query,
            documents=list(documents),
            model=self._model,
            top_k=top_k,
        )
        # Voyage returns results with scores sorted descending
        scores: list[float] = []
        for doc in documents:
            match = next((item for item in response.results if item.document == doc), None)
            if match:
                scores.append(float(match.score))
            else:
                scores.append(0.0)
        return scores


__all__ = ["OpenAIChatClient", "VoyageEmbeddingClient", "VoyageRerankClient"]
