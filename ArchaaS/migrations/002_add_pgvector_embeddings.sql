-- =============================================================================
-- Migration: Add pgvector extension and embeddings column
-- =============================================================================

-- Enable pgvector extension (requires superuser or RDS permissions)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding column to chunks table
ALTER TABLE chunks 
ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- Create HNSW index for fast similarity search
-- Using cosine distance which is optimal for normalized embeddings
CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
ON chunks USING hnsw(embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Create index for efficient filtering by document + embedding search
CREATE INDEX IF NOT EXISTS idx_chunks_document_embedding
ON chunks(document_id) INCLUDE (embedding);

-- Verify
SELECT 
    'pgvector enabled' as status,
    (SELECT extversion FROM pg_extension WHERE extname = 'vector') as version;

