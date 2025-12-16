# Product Overview

The platform delivers a LangGraph-based Agent API with document ingestion and secure auth/user services. It targets RAG workloads: upload documents via ingestion, query them through the Agent API, and rely on shared persistence and JWT-backed auth. The Swagger aggregator is optional and currently disabled.

## Problem Statement
Teams need a ready-to-run retrieval+chat backend with consistent auth and data semantics, without rebuilding ingestion pipelines, vector search, or JWT plumbing for every project.

## Core Goals
1. **Reliable retrieval + citations**: Hybrid BM25 + vector with Voyage embeddings/reranker, HyDE rewrites, and strict `[c#]` citations.
2. **Security & ownership**: Argon2id hashing, JWT rotation, per-user document ownership/attachment gating, rate limiting.
3. **Operational clarity**: Standardized uv/Python 3.13 tooling, Docker Compose workflows (local/hybrid/prod), and EC2 patch deploy runbooks.
4. **Shared data model**: Single shared data layer (`packages/shared_data_layer`) to avoid schema drift across services.

## Key Features

### Agent API (FastAPI + LangGraph)
- Chat/SSE endpoints with conversation persistence and UUID `thread_id` ownership.
- Attachment-aware retrieval: documents stay blocked until ingestion completes; structured prompts with per-fact footnotes.
- Hybrid retrieval (BM25 + pgvector) with Voyage `voyage-3-large` embeddings and `rerank-2.5`.

### Ingestion Service (FastAPI, EC2)
- MarkItDown → chunk → embed → index → activate pipeline; unique uploads to avoid dedupe shortcuts.
- Exposed at `INGEST_BASE_URL` (default `http://52.207.140.87:8085` in prod envs).

### Auth & User Services (Flask)
- JWT issuance/verification with Argon2id password hashing and rotation.
- User management endpoints; depends on separate `auth_db` database.

### Shared Data Layer
- Centralized models, repositories, and schemas used by Agent API; Postgres 16 + pgvector with two logical DBs (`housing`, `auth_db`).

### Optional Swagger Aggregator
- Node/Express/TypeScript service for aggregated docs; currently not deployed.

## User Experience
- **Developers**: Clear env selection (`use_env.sh`), Compose profiles for reduced demo vs. hybrid dev, uv-managed tooling, and smoke scripts for AWS.
- **End Users**: Secure auth, reliable document ingestion, and chat responses with transparent citations.
