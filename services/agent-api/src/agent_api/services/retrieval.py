"""Retrieval and rerank orchestration for the ReAct tools."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent_api.clients import OpenAIChatClient, VoyageEmbeddingClient, VoyageRerankClient
from agent_api.http.errors import GatewayError
from agent_api.services.retrieval_scope import (
    ConversationDocumentRecord,
    ConversationScopeRepository,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    score: float
    page_number: int | None = None
    position: int | None = None
    canonical_name: str | None = None


@dataclass(slots=True)
class RetrievalContext:
    attachments: list[ConversationDocumentRecord]
    chunks: list[RetrievedChunk]
    citations: list[dict[str, Any]]
    context_text: str


class RetrievalService:
    def __init__(
        self,
        *,
        scope_repo: ConversationScopeRepository,
        embedding_client: VoyageEmbeddingClient,
        rerank_client: VoyageRerankClient,
        chat_client: OpenAIChatClient,
        top_k: int = 8,
    ):
        self._scope_repo = scope_repo
        self._embedding_client = embedding_client
        self._rerank_client = rerank_client
        self._chat_client = chat_client
        self._top_k = top_k

    @property
    def scope_repo(self) -> ConversationScopeRepository:
        return self._scope_repo

    async def retrieve(
        self,
        *,
        user_query: str,
        conversation_id: str,
    ) -> RetrievalContext:
        attachments = await self._scope_repo.list_conversation_documents(conversation_id)
        if not attachments:
            raise GatewayError(
                code="ATTACHMENTS_REQUIRED",
                message="No documents attached to this conversation.",
                status_code=400,
            )
        summaries = await self._scope_repo.hydrate_documents([a.document_id for a in attachments])
        active_doc_ids = [
            doc_id for doc_id, summary in summaries.items() if summary.status == "active"
        ]
        if not active_doc_ids:
            raise GatewayError(
                code="DOCUMENTS_INACTIVE",
                message="Attached documents are not active yet; wait for ingestion to complete.",
                status_code=409,
            )

        expanded_queries = await self._build_query_set(user_query)
        embeddings = await self._embedding_client.embed(expanded_queries)
        retrieved = await self._run_retrieval(
            queries=expanded_queries,
            embeddings=embeddings,
            document_ids=active_doc_ids,
            summaries=summaries,
        )
        reranked = await self._rerank_chunks(query=user_query, chunks=retrieved)
        context_blocks = reranked[: self._top_k]
        context_text = self._format_context(context_blocks)
        citations = [
            {
                "doc_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "score": chunk.score,
                "canonical_name": chunk.canonical_name,
                "page_number": chunk.page_number,
                "position": chunk.position,
                "text": chunk.text,
            }
            for chunk in context_blocks
        ]
        if not citations:
            raise GatewayError(
                code="NO_RESULTS",
                message="Retrieval returned no citations.",
                status_code=502,
            )
        return RetrievalContext(
            attachments=attachments,
            chunks=context_blocks,
            citations=citations,
            context_text=context_text,
        )

    async def _build_query_set(self, user_query: str) -> list[str]:
        """Expand the user query with HyDE-style and rewrite variants."""

        queries = [user_query]
        synthetic = await self._build_hyde_query(user_query)
        if synthetic:
            queries.append(synthetic)

        rewrites = await self._rewrite_queries(user_query)
        for q in rewrites:
            if q and q not in queries:
                queries.append(q)
        return queries[:4]

    async def _run_retrieval(
        self,
        *,
        queries: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        document_ids: Sequence[str],
        summaries,
    ) -> list[RetrievedChunk]:
        results: dict[str, RetrievedChunk] = {}
        previews = await self._scope_repo.load_document_chunk_previews(
            document_ids=document_ids,
            chunk_types=("text",),
            max_chars_per_doc=2400,
            max_chunks_per_doc=self._top_k,
        )

        for query, embedding in zip(queries, embeddings, strict=False):
            hybrid = await self._scope_repo.hybrid_chunk_search(
                query=query,
                document_ids=document_ids,
                embedding=embedding,
                top_k=self._top_k,
                hybrid_weight=0.6,
                chunk_types=("text",),
            )
            for doc_id, chunks in hybrid.items():
                doc_name = None
                summary = summaries.get(doc_id)
                if summary:
                    doc_name = summary.canonical_name or doc_id
                else:
                    for preview in previews.get(doc_id, []):
                        doc_name = preview.document_id
                        break
                for chunk in chunks:
                    key = f"{doc_id}:{chunk.chunk_id}"
                    score = float(chunk.score or 0.0)
                    existing = results.get(key)
                    if existing is None or score > existing.score:
                        results[key] = RetrievedChunk(
                            chunk_id=chunk.chunk_id,
                            document_id=doc_id,
                            text=chunk.text,
                            score=score,
                            page_number=chunk.page_number,
                            position=chunk.position,
                            canonical_name=doc_name,
                        )
        return sorted(results.values(), key=lambda c: c.score, reverse=True)

    async def _rerank_chunks(
        self, *, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        documents = [chunk.text for chunk in chunks]
        scores = await self._rerank_client.rerank(query, documents, top_k=len(documents))
        scored = []
        for chunk, score in zip(chunks, scores, strict=False):
            scored.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    text=chunk.text,
                    score=float(score or chunk.score),
                    page_number=chunk.page_number,
                    position=chunk.position,
                    canonical_name=chunk.canonical_name,
                )
            )
        return sorted(scored, key=lambda c: c.score, reverse=True)

    async def _build_hyde_query(self, user_query: str) -> str | None:
        prompt = [
            {
                "role": "system",
                "content": "Generate a concise hypothetical answer or expansion that would retrieve the best supporting evidence.",
            },
            {"role": "user", "content": user_query},
        ]
        try:
            return await self._chat_client.complete(prompt, temperature=0.3, max_tokens=128)
        except Exception:
            logger.warning("HyDE generation failed; continuing without synthetic query")
            return None

    async def _rewrite_queries(self, user_query: str) -> list[str]:
        prompt = [
            {
                "role": "system",
                "content": (
                    "Rewrite the question into 2 concise variants that may retrieve different evidence. "
                    "Return each variant on its own line without numbering."
                ),
            },
            {"role": "user", "content": user_query},
        ]
        try:
            text = await self._chat_client.complete(prompt, temperature=0.5, max_tokens=160)
        except Exception:
            logger.warning("Query rewrite failed; continuing without rewrites")
            return []
        lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
        return [line for line in lines if line]

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            header = f"[c{idx}] {chunk.canonical_name or chunk.document_id}"
            location = []
            if chunk.page_number is not None:
                location.append(f"page {chunk.page_number}")
            if chunk.position is not None:
                location.append(f"pos {chunk.position}")
            if location:
                header += f" ({', '.join(location)})"
            lines.append(f"{header}\n{chunk.text}")
        return "\n\n".join(lines)


__all__ = ["RetrievalContext", "RetrievalService", "RetrievedChunk"]
