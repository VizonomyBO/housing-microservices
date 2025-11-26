"""
Document Repository for database operations.

Uses asyncpg for async PostgreSQL operations.
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
    
    async def find_by_owner_and_hash(
        self,
        owner_user_id: str,
        content_hash: str,
    ) -> Optional[dict[str, Any]]:
        """
        Find document by owner_user_id and content_hash for deduplication.
        
        This implements the hash-based deduplication check per the schema:
        Unique constraint on (owner_user_id, content_hash) for user docs.
        
        Args:
            owner_user_id: The document owner's user ID
            content_hash: SHA-256 hash of document content (stored exactly as provided)
        
        Returns:
            Document record if found, None otherwise
        """
        pool = await self._get_pool()
        
        # Full column list per database_schema_persistence_rules.md
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
                
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise DatabaseError(f"Failed to query documents: {e}")
    
    async def create_document(self, document_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new document record.
        
        Full column list per database_schema_persistence_rules.md
        
        Args:
            document_data: Document data dictionary with all required fields
        
        Returns:
            Created document record
        """
        pool = await self._get_pool()
        
        query = """
            INSERT INTO documents (
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
                visibility,
                managed_by,
                metadata,
                created_at,
                updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $17
            )
            RETURNING *
        """
        
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    document_data["id"],
                    document_data.get("owner_user_id"),
                    document_data["access_scope"],
                    document_data["canonical_name"],
                    document_data["country_code"],
                    document_data["language"],
                    document_data.get("tags", []),
                    document_data["status"],
                    document_data.get("ingestion_stage"),
                    document_data.get("content_hash"),  # Stored exactly as provided
                    document_data["source_uri"],
                    document_data["byte_size"],
                    document_data.get("ingestion_started_at"),
                    document_data.get("visibility", "private"),
                    document_data.get("managed_by", "user"),
                    json.dumps(document_data.get("metadata", {})),  # Serialize dict to JSON string
                    document_data["created_at"],
                )
                
                logger.info(
                    f"Created document record",
                    extra={"document_id": document_data["id"]},
                )
                return dict(row)
        except asyncpg.UniqueViolationError as e:
            logger.warning(
                f"Duplicate document detected: {e}",
                extra={"document_id": document_data["id"]},
            )
            raise DatabaseError("Document with this content already exists")
        except Exception as e:
            logger.error(f"Failed to create document: {e}")
            raise DatabaseError(f"Failed to create document: {e}")
    
    async def delete_document(self, document_id: str) -> bool:
        """
        Delete a document record (hard delete for rollback scenarios).
        
        Args:
            document_id: The document ID to delete
        
        Returns:
            True if deleted, False if not found
        """
        pool = await self._get_pool()
        
        query = """
            DELETE FROM documents
            WHERE id = $1
            RETURNING id
        """
        
        try:
            async with pool.acquire() as conn:
                result = await conn.fetchrow(query, document_id)
                return result is not None
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise DatabaseError(f"Failed to delete document: {e}")
    
    async def update_document_status(
        self,
        document_id: str,
        status: str,
        ingestion_stage: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Update document status and optionally the ingestion stage.
        
        Args:
            document_id: The document ID to update
            status: New status value
            ingestion_stage: Optional new ingestion stage
        
        Returns:
            Updated document record or None if not found
        """
        pool = await self._get_pool()
        
        if ingestion_stage:
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
    
    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

