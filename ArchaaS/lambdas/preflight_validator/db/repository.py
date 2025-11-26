"""
Document Repository for database operations.

Uses asyncpg for async PostgreSQL operations.
Extended for preflight validation operations.
"""
import json
import os
from typing import Any, Optional

import asyncpg

from core.exceptions import DatabaseError
from core.logging import get_logger

logger = get_logger(__name__)

# Database configuration from environment
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://vizonomy_user:postgres@localhost:5432/housing"
)


class DocumentRepository:
    """
    Repository for document database operations.
    
    Implements async database access using asyncpg connection pool.
    Extended with methods needed for preflight validation.
    """
    
    _pool: Optional[asyncpg.Pool] = None
    
    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create the connection pool."""
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=10,
                    command_timeout=30,
                )
            except Exception as e:
                logger.error(f"Failed to create database pool: {e}")
                raise DatabaseError(f"Database connection failed: {e}")
        return self._pool
    
    async def get_document_by_id(self, document_id: str) -> Optional[dict[str, Any]]:
        """
        Get document by ID.
        
        Full column list per database_schema_persistence_rules.md
        
        Args:
            document_id: The document ID
        
        Returns:
            Document record or None if not found
        """
        pool = await self._get_pool()
        
        query = """
            SELECT 
                id,
                owner_user_id,
                access_scope,
                canonical_name,
                country_code,
                language,
                tags,
                status,
                ingestion_stage,
                content_hash,
                source_uri,
                byte_size,
                ingestion_started_at,
                ingestion_completed_at,
                visibility,
                managed_by,
                active_chat_refs,
                metadata,
                created_at,
                updated_at,
                deleted_at
            FROM documents
            WHERE id = $1
              AND deleted_at IS NULL
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, document_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise DatabaseError(f"Failed to query document: {e}")
    
    async def find_by_owner_and_hash(
        self,
        owner_user_id: str,
        content_hash: str,
    ) -> Optional[dict[str, Any]]:
        """
        Find document by owner_user_id and content_hash for deduplication.
        
        Full column list per database_schema_persistence_rules.md
        
        Args:
            owner_user_id: The document owner's user ID
            content_hash: SHA-256 hash of document content
        
        Returns:
            Document record if found, None otherwise
        """
        pool = await self._get_pool()
        
        query = """
            SELECT 
                id,
                owner_user_id,
                access_scope,
                canonical_name,
                country_code,
                language,
                tags,
                status,
                ingestion_stage,
                content_hash,
                source_uri,
                byte_size,
                ingestion_started_at,
                ingestion_completed_at,
                visibility,
                managed_by,
                active_chat_refs,
                metadata,
                created_at,
                updated_at,
                deleted_at
            FROM documents
            WHERE owner_user_id = $1
              AND content_hash = $2
              AND deleted_at IS NULL
              AND status NOT IN ('failed', 'archived')
            LIMIT 1
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, owner_user_id, content_hash)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise DatabaseError(f"Failed to query documents: {e}")
    
    async def update_document_status(
        self,
        document_id: str,
        status: str,
        ingestion_stage: Optional[str] = None,
        ingestion_started_at: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Update document status and optionally the ingestion stage.
        
        Per database_schema_persistence_rules.md, also tracks ingestion timing.
        
        Args:
            document_id: The document ID to update
            status: New status value
            ingestion_stage: Optional new ingestion stage
            ingestion_started_at: Optional ingestion start timestamp
        
        Returns:
            Updated document record or None if not found
        """
        pool = await self._get_pool()
        
        if ingestion_stage and ingestion_started_at:
            query = """
                UPDATE documents
                SET status = $2,
                    ingestion_stage = $3,
                    ingestion_started_at = $4,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """
            params = (document_id, status, ingestion_stage, ingestion_started_at)
        elif ingestion_stage:
            query = """
                UPDATE documents
                SET status = $2,
                    ingestion_stage = $3,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """
            params = (document_id, status, ingestion_stage)
        else:
            query = """
                UPDATE documents
                SET status = $2,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
            """
            params = (document_id, status)
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to update document status: {e}")
            raise DatabaseError(f"Failed to update document: {e}")
    
    async def update_document_content_hash(
        self,
        document_id: str,
        content_hash: str,
    ) -> Optional[dict[str, Any]]:
        """
        Update document content hash (when computed post-upload).
        
        Args:
            document_id: The document ID
            content_hash: Computed SHA-256 hash
        
        Returns:
            Updated document record
        """
        pool = await self._get_pool()
        
        query = """
            UPDATE documents
            SET content_hash = $2,
                updated_at = NOW()
            WHERE id = $1
            RETURNING id, content_hash
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, document_id, content_hash)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to update content hash: {e}")
            raise DatabaseError(f"Failed to update document: {e}")
    
    async def update_document_artifacts(
        self,
        document_id: str,
        artifacts: dict[str, str],
    ) -> Optional[dict[str, Any]]:
        """
        Update document metadata with artifact URIs.
        
        Args:
            document_id: The document ID
            artifacts: Dictionary of artifact type -> S3 URI
        
        Returns:
            Updated document record
        """
        pool = await self._get_pool()
        
        # Merge artifacts into existing metadata
        query = """
            UPDATE documents
            SET metadata = COALESCE(metadata, '{}'::jsonb) || $2::jsonb,
                updated_at = NOW()
            WHERE id = $1
            RETURNING id, metadata
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    document_id,
                    json.dumps({"artifacts": artifacts}),
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to update artifacts: {e}")
            raise DatabaseError(f"Failed to update document: {e}")
    
    async def mark_ingestion_completed(
        self,
        document_id: str,
        status: str = "active",
    ) -> Optional[dict[str, Any]]:
        """
        Mark document ingestion as completed.
        
        Per database_schema_persistence_rules.md, sets ingestion_completed_at
        and updates status to 'active'.
        
        Args:
            document_id: The document ID
            status: Final status (default 'active')
        
        Returns:
            Updated document record
        """
        pool = await self._get_pool()
        
        query = """
            UPDATE documents
            SET status = $2,
                ingestion_completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, document_id, status)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to mark ingestion completed: {e}")
            raise DatabaseError(f"Failed to update document: {e}")
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

