"""LLM and embedding client adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from langchain_core.documents import Document
from langchain_voyageai import VoyageAIEmbeddings, VoyageAIRerank
from openai import AsyncOpenAI


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
        self._client = VoyageAIEmbeddings(model=model, api_key=api_key)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._client.embed_documents, list(texts))


class VoyageRerankClient:
    def __init__(self, *, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    async def rerank(self, query: str, documents: Sequence[str], top_k: int) -> list[float]:
        return await asyncio.to_thread(self._rerank_sync, query, documents, top_k)

    def _rerank_sync(self, query: str, documents: Sequence[str], top_k: int) -> list[float]:
        reranker = VoyageAIRerank(
            model=self._model,
            voyage_api_key=self._api_key,
            top_k=top_k,
        )
        doc_objs = [
            Document(page_content=doc, metadata={"idx": idx}) for idx, doc in enumerate(documents)
        ]
        ranked = reranker.compress_documents(documents=doc_objs, query=query)
        scores = [0.0 for _ in documents]
        for doc in ranked:
            idx = doc.metadata.get("idx")
            if idx is None:
                continue
            score = doc.metadata.get("relevance_score") or 0.0
            scores[int(idx)] = float(score)
        return scores


__all__ = ["OpenAIChatClient", "VoyageEmbeddingClient", "VoyageRerankClient"]
