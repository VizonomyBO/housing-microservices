"""
Embedding Writer Lambda - Generates embeddings with Voyage AI and stores in PostgreSQL.

Reads chunks from S3, generates embeddings via Voyage AI, and persists to chunks table.
"""
import json
import os
import logging
from typing import Any, List, Dict
from uuid import UUID

import boto3
import httpx
import asyncpg

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_MODEL = os.environ.get("VOYAGE_MODEL", "voyage-3-lite")
VOYAGE_API_URL = "https://api.voyageai.com/v1/embeddings"
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
DATABASE_HOST = os.environ.get("DATABASE_HOST", "")
DATABASE_PORT = int(os.environ.get("DATABASE_PORT", "5432"))
DATABASE_NAME = os.environ.get("DATABASE_NAME", "housing")
DATABASE_USER = os.environ.get("DATABASE_USER", "vizonomy_user")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD", "")
BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))
EMBEDDING_DIM = 1024  # Voyage-3-lite dimension

# S3 client
s3 = boto3.client("s3")


async def get_db_connection():
    """Get async database connection."""
    return await asyncpg.connect(
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        database=DATABASE_NAME,
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
    )


async def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using Voyage AI API."""
    if not texts:
        return []
    
    headers = {
        "Authorization": f"Bearer {VOYAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": VOYAGE_MODEL,
        "input": texts,
        "input_type": "document",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            VOYAGE_API_URL,
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        
    # Extract embeddings in order
    embeddings = [item["embedding"] for item in data["data"]]
    logger.info(f"Generated {len(embeddings)} embeddings, dim={len(embeddings[0]) if embeddings else 0}")
    return embeddings


async def store_chunks_with_embeddings(
    conn: asyncpg.Connection,
    document_id: str,
    chunks: List[Dict],
    embeddings: List[List[float]],
) -> int:
    """Store chunks with embeddings in PostgreSQL."""
    
    # Check if embedding column exists
    column_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'chunks' AND column_name = 'embedding'
        )
    """)
    
    inserted = 0
    for chunk, embedding in zip(chunks, embeddings):
        content = chunk.get("content", "")
        chunk_index = chunk.get("chunk_index", 0)
        page_numbers = chunk.get("page_numbers", [])
        section_title = chunk.get("section_title")
        token_count = chunk.get("token_count", 0)
        
        # Generate a new UUID for each chunk (chunk IDs from manifest aren't UUIDs)
        import uuid as uuid_mod
        chunk_uuid = uuid_mod.uuid4()
        
        if column_exists:
            # Format embedding as pgvector string: [1.0, 2.0, ...]
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
            
            # Store with embedding vector
            await conn.execute("""
                INSERT INTO chunks (
                    id, document_id, text_content, position, token_count,
                    section_path, page_number, chunk_type, embedding
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'text', $8::vector)
            """,
                chunk_uuid,
                UUID(document_id),
                content,
                chunk_index,
                token_count,
                [section_title] if section_title else [],
                page_numbers[0] if page_numbers else None,
                embedding_str,
            )
        else:
            # Store without embedding (fallback)
            await conn.execute("""
                INSERT INTO chunks (
                    id, document_id, text_content, position, token_count,
                    section_path, page_number, chunk_type
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'text')
            """,
                chunk_uuid,
                UUID(document_id),
                content,
                chunk_index,
                token_count,
                [section_title] if section_title else [],
                page_numbers[0] if page_numbers else None,
            )
        
        inserted += 1
    
    return inserted


def handler(event: dict, context: Any) -> dict:
    """
    Process chunks and generate embeddings.
    
    Input:
    {
        "document_id": "uuid",
        "ingestion_id": "uuid",
        "trace_id": "uuid"
    }
    """
    import asyncio
    return asyncio.get_event_loop().run_until_complete(async_handler(event))


async def async_handler(event: dict) -> dict:
    """Async handler for embedding generation."""
    logger.info(f"Embedding writer started: {json.dumps(event)}")
    
    document_id = event.get("document_id")
    ingestion_id = event.get("ingestion_id")
    trace_id = event.get("trace_id")
    
    if not document_id:
        return {
            "statusCode": 400,
            "error": "Missing document_id"
        }
    
    try:
        # Read chunks from S3
        chunks_key = f"processed/{document_id}/chunks.jsonl"
        logger.info(f"Reading chunks from s3://{PROCESSED_BUCKET}/{chunks_key}")
        
        response = s3.get_object(Bucket=PROCESSED_BUCKET, Key=chunks_key)
        chunks_data = response["Body"].read().decode("utf-8")
        
        chunks = [json.loads(line) for line in chunks_data.strip().split("\n") if line.strip()]
        logger.info(f"Loaded {len(chunks)} chunks for document {document_id}")
        
        if not chunks:
            return {
                "statusCode": 200,
                "document_id": document_id,
                "ingestion_id": ingestion_id,
                "embeddings_written": 0,
                "message": "No chunks to embed"
            }
        
        # Generate embeddings in batches
        all_embeddings = []
        texts = [c.get("content", "") for c in chunks]
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            logger.info(f"Processing batch {i // BATCH_SIZE + 1}/{(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE}")
            batch_embeddings = await generate_embeddings(batch)
            all_embeddings.extend(batch_embeddings)
        
        logger.info(f"Generated {len(all_embeddings)} embeddings total")
        
        # Store in database
        conn = await get_db_connection()
        try:
            inserted = await store_chunks_with_embeddings(
                conn, document_id, chunks, all_embeddings
            )
            logger.info(f"Stored {inserted} chunks with embeddings")
        finally:
            await conn.close()
        
        return {
            "statusCode": 200,
            "document_id": document_id,
            "ingestion_id": ingestion_id,
            "embeddings_written": len(all_embeddings),
            "chunks_processed": len(chunks),
        }
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "error": str(e),
            "document_id": document_id,
        }
