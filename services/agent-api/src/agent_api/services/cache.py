"""Chat response cache service."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared_data_layer.db.models import ChatResponseCache

logger = logging.getLogger(__name__)


class ChatCacheService:
    """Service for managing chat response caching."""

    def __init__(self, db_session: AsyncSession):
        self._session = db_session

    @staticmethod
    def _hash_question(question: str) -> str:
        """Generate SHA256 hash of the question for cache key."""
        return hashlib.sha256(question.encode("utf-8")).hexdigest()

    async def get_cached_response(
        self, country_code: str, question: str
    ) -> dict[str, Any] | None:
        """
        Retrieve cached response for a given country and question.

        Args:
            country_code: ISO-3 country code
            question: User question text

        Returns:
            Cached response dict or None if not found
        """
        question_hash = self._hash_question(question)
        stmt = select(ChatResponseCache).where(
            ChatResponseCache.country_code == country_code,
            ChatResponseCache.question_hash == question_hash,
        )
        result = await self._session.execute(stmt)
        cache_entry = result.scalar_one_or_none()

        if cache_entry:
            logger.info(
                "Cache hit",
                extra={
                    "country_code": country_code,
                    "question_hash": question_hash,
                },
            )
            return cache_entry.response

        logger.info(
            "Cache miss",
            extra={
                "country_code": country_code,
                "question_hash": question_hash,
            },
        )
        return None

    async def store_response(
        self, country_code: str, question: str, response: dict[str, Any]
    ) -> None:
        """
        Store a chat response in the cache.

        Args:
            country_code: ISO-3 country code
            question: User question text
            response: Response data to cache
        """
        question_hash = self._hash_question(question)

        # Check if entry exists
        stmt = select(ChatResponseCache).where(
            ChatResponseCache.country_code == country_code,
            ChatResponseCache.question_hash == question_hash,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing entry
            existing.response = response
            logger.info(
                "Updated cache entry",
                extra={
                    "country_code": country_code,
                    "question_hash": question_hash,
                },
            )
        else:
            # Create new entry
            cache_entry = ChatResponseCache(
                country_code=country_code,
                question=question,
                question_hash=question_hash,
                response=response,
            )
            self._session.add(cache_entry)
            logger.info(
                "Created cache entry",
                extra={
                    "country_code": country_code,
                    "question_hash": question_hash,
                },
            )

        await self._session.commit()

    async def clear_cache(self, country_code: str, question: str) -> bool:
        """
        Clear cache entry for a specific country and question.

        Args:
            country_code: ISO-3 country code
            question: User question text

        Returns:
            True if entry was deleted, False if not found
        """
        question_hash = self._hash_question(question)
        stmt = delete(ChatResponseCache).where(
            ChatResponseCache.country_code == country_code,
            ChatResponseCache.question_hash == question_hash,
        )
        result = await self._session.execute(stmt)
        await self._session.commit()

        deleted = result.rowcount > 0
        if deleted:
            logger.info(
                "Cleared cache entry",
                extra={
                    "country_code": country_code,
                    "question_hash": question_hash,
                },
            )
        else:
            logger.info(
                "No cache entry to clear",
                extra={
                    "country_code": country_code,
                    "question_hash": question_hash,
                },
            )

        return deleted


__all__ = ["ChatCacheService"]

