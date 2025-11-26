-- Migration: 001_create_documents_table
-- Description: Complete database schema for document upload, deduplication, and ingestion
-- Based on: database_schema_persistence_rules.md

BEGIN;

-- =============================================================================
-- EXTENSIONS
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- For vector embeddings (optional - install pgvector if needed)
-- CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

-- Document status lifecycle
DO $$ BEGIN
    CREATE TYPE document_status AS ENUM (
        'PENDING_UPLOAD',
        'registered',
        'validating',
        'ingesting',
        'active',
        'failed',
        'archived'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Access scope for documents
DO $$ BEGIN
    CREATE TYPE access_scope AS ENUM (
        'base',
        'user_private',
        'user_shared'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Ingestion pipeline stages
DO $$ BEGIN
    CREATE TYPE ingestion_stage AS ENUM (
        'preflight',
        'convert',
        'chunk',
        'embed',
        'index',
        'activate'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Ingestion job status
DO $$ BEGIN
    CREATE TYPE job_status AS ENUM (
        'pending',
        'running',
        'succeeded',
        'failed',
        'canceled'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Artifact types
DO $$ BEGIN
    CREATE TYPE artifact_type AS ENUM (
        'markdown',
        'table_json',
        'figure_image',
        'chunk_manifest',
        'pdf_export'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Chunk types
DO $$ BEGIN
    CREATE TYPE chunk_type AS ENUM (
        'text',
        'table',
        'image'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- User status
DO $$ BEGIN
    CREATE TYPE user_status AS ENUM (
        'active',
        'suspended',
        'deleted'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Conversation status
DO $$ BEGIN
    CREATE TYPE conversation_status AS ENUM (
        'active',
        'archived',
        'deleted'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Attachment source
DO $$ BEGIN
    CREATE TYPE attach_source AS ENUM (
        'base_auto',
        'user_upload',
        'admin_attach'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Visibility override
DO $$ BEGIN
    CREATE TYPE visibility_override AS ENUM (
        'visible',
        'hidden',
        'read_only'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Document role in conversation
DO $$ BEGIN
    CREATE TYPE document_role AS ENUM (
        'primary',
        'supplemental'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Pillar answer status
DO $$ BEGIN
    CREATE TYPE pillar_status AS ENUM (
        'draft',
        'running',
        'published',
        'superseded',
        'rejected'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- TABLE: users (Identity)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_ref TEXT UNIQUE NOT NULL,
    status user_status NOT NULL DEFAULT 'active',
    roles TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_external_ref ON users(external_ref);
CREATE INDEX IF NOT EXISTS idx_users_active ON users(status) WHERE status = 'active';

-- =============================================================================
-- TABLE: documents (Document Registry)
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    access_scope access_scope NOT NULL DEFAULT 'user_private',
    canonical_name TEXT NOT NULL,
    country_code CHAR(3),
    language TEXT DEFAULT 'en',
    tags TEXT[] DEFAULT '{}',
    status document_status NOT NULL DEFAULT 'PENDING_UPLOAD',
    ingestion_stage ingestion_stage,
    content_hash TEXT,
    source_uri TEXT,
    byte_size BIGINT,
    ingestion_started_at TIMESTAMPTZ,
    ingestion_completed_at TIMESTAMPTZ,
    visibility TEXT DEFAULT 'private',
    managed_by TEXT DEFAULT 'user',
    active_chat_refs INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    -- Constraints
    CONSTRAINT chk_base_no_owner CHECK (
        access_scope <> 'base' OR owner_user_id IS NULL
    ),
    CONSTRAINT chk_positive_refs CHECK (active_chat_refs >= 0),
    CONSTRAINT chk_positive_size CHECK (byte_size IS NULL OR byte_size > 0)
);

-- Hash-based deduplication: unique (owner_user_id, content_hash) for user docs
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_owner_hash
    ON documents (owner_user_id, content_hash)
    WHERE owner_user_id IS NOT NULL
      AND content_hash IS NOT NULL
      AND deleted_at IS NULL;

-- Base document deduplication: unique per country per hash
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_base_country_hash
    ON documents (access_scope, country_code, content_hash)
    WHERE access_scope = 'base'
      AND content_hash IS NOT NULL
      AND deleted_at IS NULL;

-- Unique canonical name per user for active documents
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_owner_name
    ON documents (owner_user_id, lower(canonical_name))
    WHERE deleted_at IS NULL
      AND access_scope <> 'base';

-- Query optimization indexes
CREATE INDEX IF NOT EXISTS idx_documents_access_country ON documents(access_scope, country_code);
CREATE INDEX IF NOT EXISTS idx_documents_status_updated ON documents(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_pending_ingestion ON documents(status) 
    WHERE status IN ('PENDING_UPLOAD', 'validating', 'ingesting', 'failed');
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_documents_tags ON documents USING GIN(tags);

-- =============================================================================
-- TABLE: ingestion_jobs
-- =============================================================================
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    stage ingestion_stage NOT NULL,
    status job_status NOT NULL DEFAULT 'pending',
    attempt SMALLINT DEFAULT 0,
    worker TEXT,
    last_error JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    trace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_document_stage ON ingestion_jobs(document_id, stage);
CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_pending ON ingestion_jobs(status) 
    WHERE status IN ('pending', 'failed');

-- =============================================================================
-- TABLE: artifacts
-- =============================================================================
CREATE TABLE IF NOT EXISTS artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    artifact_type artifact_type NOT NULL,
    s3_uri TEXT NOT NULL,
    byte_size BIGINT,
    content_hash TEXT,
    page_range INT4RANGE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_document_type ON artifacts(document_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_metadata ON artifacts USING GIN(metadata);

-- =============================================================================
-- TABLE: conversations
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    country_code CHAR(3),
    status conversation_status NOT NULL DEFAULT 'active',
    document_scope JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);

-- =============================================================================
-- TABLE: conversation_documents (Chat ↔ Document mapping)
-- =============================================================================
CREATE TABLE IF NOT EXISTS conversation_documents (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    attached_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    attach_source attach_source NOT NULL DEFAULT 'user_upload',
    role document_role DEFAULT 'primary',
    visibility_override visibility_override DEFAULT 'visible',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,

    PRIMARY KEY (conversation_id, document_id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_documents_document ON conversation_documents(document_id);
CREATE INDEX IF NOT EXISTS idx_conversation_documents_source ON conversation_documents(attach_source);

-- =============================================================================
-- TABLE: chunks (Retrieval Units)
-- =============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content_hash TEXT,
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    country_code CHAR(3),
    chunk_type chunk_type NOT NULL DEFAULT 'text',
    page_number INTEGER,
    section_path TEXT[] DEFAULT '{}',
    position INTEGER NOT NULL,
    token_count INTEGER,
    text_content TEXT,
    text_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text_content, ''))) STORED,
    schema_summary TEXT,
    table_payload JSONB,
    image_caption TEXT,
    bbox JSONB,
    -- embedding vector(1024), -- Uncomment if pgvector is installed
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_token_count CHECK (token_count IS NULL OR token_count <= 800)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id, chunk_type, position);
CREATE INDEX IF NOT EXISTS idx_chunks_country_type ON chunks(country_code, chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_text_search ON chunks USING GIN(text_tsv);
-- CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw(embedding vector_cosine_ops); -- Uncomment if pgvector

-- =============================================================================
-- TABLE: chunk_metrics
-- =============================================================================
CREATE TABLE IF NOT EXISTS chunk_metrics (
    chunk_id UUID PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    quality_score NUMERIC(3,2),
    retrieval_count BIGINT DEFAULT 0,
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- TABLE: messages
-- =============================================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT,
    citations JSONB DEFAULT '[]',
    tool_calls JSONB DEFAULT '[]',
    interrupt JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

-- =============================================================================
-- TABLE: message_tool_calls
-- =============================================================================
CREATE TABLE IF NOT EXISTS message_tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input JSONB NOT NULL,
    output JSONB,
    status TEXT,
    latency_ms INTEGER,
    error JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_tool_calls_message ON message_tool_calls(message_id);

-- =============================================================================
-- TABLE: message_citations
-- =============================================================================
CREATE TABLE IF NOT EXISTS message_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE RESTRICT,
    citation_key TEXT NOT NULL,
    evidence_text TEXT,
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(message_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_message_citations_message ON message_citations(message_id);
CREATE INDEX IF NOT EXISTS idx_message_citations_chunk ON message_citations(chunk_id);

-- =============================================================================
-- TABLE: agent_state_checkpoints
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_state_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    node_name TEXT NOT NULL,
    serialized_state BYTEA NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_conversation ON agent_state_checkpoints(conversation_id, created_at DESC);

-- =============================================================================
-- TABLE: pillar_answers
-- =============================================================================
CREATE TABLE IF NOT EXISTS pillar_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    country_code CHAR(3) NOT NULL,
    pillar_name TEXT NOT NULL,
    document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    content_hash TEXT,
    score NUMERIC(4,3),
    summary_markdown TEXT,
    answer_json JSONB,
    status pillar_status NOT NULL DEFAULT 'draft',
    generated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pillar_answers_published
    ON pillar_answers(owner_user_id, country_code, pillar_name, status)
    WHERE status = 'published';
CREATE INDEX IF NOT EXISTS idx_pillar_answers_country ON pillar_answers(country_code, pillar_name);

-- =============================================================================
-- TABLE: pillar_answer_sources
-- =============================================================================
CREATE TABLE IF NOT EXISTS pillar_answer_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pillar_answer_id UUID NOT NULL REFERENCES pillar_answers(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    contribution_type TEXT,
    weight NUMERIC(3,2),
    evidence_text TEXT,
    page_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(pillar_answer_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_pillar_sources_answer ON pillar_answer_sources(pillar_answer_id);

-- =============================================================================
-- TABLE: retrieval_runs
-- =============================================================================
CREATE TABLE IF NOT EXISTS retrieval_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    query_text TEXT NOT NULL,
    document_scope JSONB DEFAULT '{}',
    hybrid_k INTEGER,
    retrieval_mode TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_runs_conversation ON retrieval_runs(conversation_id);

-- =============================================================================
-- TABLE: retrieval_run_items
-- =============================================================================
CREATE TABLE IF NOT EXISTS retrieval_run_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    retrieval_run_id UUID NOT NULL REFERENCES retrieval_runs(id) ON DELETE CASCADE,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    score NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_items_run ON retrieval_run_items(retrieval_run_id);

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to documents
DROP TRIGGER IF EXISTS trigger_documents_updated_at ON documents;
CREATE TRIGGER trigger_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply to users
DROP TRIGGER IF EXISTS trigger_users_updated_at ON users;
CREATE TRIGGER trigger_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply to conversations
DROP TRIGGER IF EXISTS trigger_conversations_updated_at ON conversations;
CREATE TRIGGER trigger_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply to chunk_metrics
DROP TRIGGER IF EXISTS trigger_chunk_metrics_updated_at ON chunk_metrics;
CREATE TRIGGER trigger_chunk_metrics_updated_at
    BEFORE UPDATE ON chunk_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- TRIGGER: Maintain active_chat_refs on conversation_documents changes
-- =============================================================================
CREATE OR REPLACE FUNCTION update_document_chat_refs()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE documents
        SET active_chat_refs = active_chat_refs + 1
        WHERE id = NEW.document_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE documents
        SET active_chat_refs = GREATEST(active_chat_refs - 1, 0)
        WHERE id = OLD.document_id;
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' AND NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
        -- Soft delete
        UPDATE documents
        SET active_chat_refs = GREATEST(active_chat_refs - 1, 0)
        WHERE id = NEW.document_id;
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_conversation_documents_refs ON conversation_documents;
CREATE TRIGGER trigger_conversation_documents_refs
    AFTER INSERT OR DELETE OR UPDATE ON conversation_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_document_chat_refs();

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Active chunks view (only from active documents)
CREATE OR REPLACE VIEW active_chunks AS
SELECT c.*
FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.status = 'active'
  AND d.deleted_at IS NULL;

-- Base documents by country (for admin UI)
CREATE OR REPLACE VIEW base_documents_by_country AS
SELECT *
FROM documents
WHERE access_scope = 'base'
  AND deleted_at IS NULL
ORDER BY country_code, canonical_name;

-- =============================================================================
-- COMMENTS
-- =============================================================================
COMMENT ON TABLE documents IS 'Document registry for uploads (base + user), tracking ingestion stages and dedup metadata';
COMMENT ON COLUMN documents.content_hash IS 'SHA-256 hash of normalized bytes; stored exactly as provided by client for S3 validation matching';
COMMENT ON COLUMN documents.owner_user_id IS 'FK to users.id, nullable for base documents';
COMMENT ON COLUMN documents.active_chat_refs IS 'Cached count of conversation attachments, maintained via trigger';

COMMENT ON TABLE conversation_documents IS 'Chat to document mapping with visibility overrides and ref counting';
COMMENT ON TABLE chunks IS 'Embeddable units for retrieval, partitioned by country_code';
COMMENT ON TABLE pillar_answers IS 'Pre-computed answers for pillars by country';

COMMIT;

