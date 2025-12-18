# Architecture

## System Overview

Modern LangGraph-centric stack with FastAPI gateways, a FastAPI ingestion pipeline on EC2, Flask auth/user services, and an optional Swagger aggregator. Postgres 16 + pgvector backs both retrieval and auth, separated into `housing` and `auth_db` databases. Docker Compose orchestrates local/hybrid/prod profiles.

## Architecture Diagram

```mermaid
flowchart LR
    Client -->|chat/upload| AgentAPI[Agent API (FastAPI + LangGraph)]
    Client -->|auth| Auth[Auth Service (Flask)]
    Client -->|users| User[User Service (Flask)]
    AgentAPI -->|trigger ingest| Ingest[Ingestion Service (FastAPI, EC2)]
    AgentAPI <-->|JWT verify| Auth
    AgentAPI -->|retrieval| HousingDB[(Postgres 16 + pgvector<br/>housing DB)]
    Auth --> AuthDB[(Postgres 16<br/>auth_db)]
    User --> AuthDB
    Ingest --> HousingDB
    Swagger[Swagger Aggregator (Node/TS, optional)] -.-> AgentAPI
```

## Component Details

### Agent API
- **Tech**: FastAPI, LangGraph, Pydantic v2, SQLAlchemy 2.x, langchain-voyageai embeddings/rerankers (required).
- **Responsibilities**: Chat/SSE, attachments, hybrid retrieval (BM25 + vector + rerank), citation-rich responses, conversation ownership (UUID `thread_id`). `/v1/documents/upload` is a proxy to the ingestion service; no inline ingestion path remains.
- **Persistence**: Uses shared data layer models/repos against `housing` DB.

### Ingestion Service
- **Tech**: FastAPI (Python 3.13 via `uv`), MarkItDown, langchain-voyageai embeddings, LangChain text splitter (RecursiveCharacterTextSplitter).
- **Flow**: Upload → MarkItDown extraction → chunk (LangChain) → embed (Voyage) → pgvector index → activate document.
- **Deployment**: EC2 service at `INGEST_BASE_URL` (default `http://52.207.140.87:8085`); replaces Lambda/S3 path and is the only supported ingestion path.

### Auth Service
- **Tech**: Flask, SQLAlchemy, Argon2, PyJWT, Flask-Limiter.
- **Responsibilities**: JWT issuance/validation, password hashing, rate limits, health endpoints; writes to `auth_db`.

### User Service
- **Tech**: Flask; depends on auth-service for token validation.
- **Responsibilities**: User profile management; uses `auth_db`.

### Shared Data Layer
- **Location**: `packages/shared_data_layer`.
- **Role**: Source of truth for SQLAlchemy models, repositories, schemas (documents, conversations, checkpoints, etc.).
- **Usage**: Imported by Agent API; integration tests rely on its Testcontainers fixtures.

### PostgreSQL
- **Version**: 16 with `pgvector`.
- **Databases**: `housing` (Agent API/shared) and `auth_db` (auth/user); keep schemas separate.
- **Init flow**: Base image `pgvector/pgvector:pg16` with `scripts/init-databases.sh` creating both DBs; a dedicated `init-migrations` container (built from `docker/init-migrations/Dockerfile`) waits for DB readiness and runs shared_data_layer Alembic migrations before app services start (compose uses `condition: service_completed_successfully` to gate agent/ingestion).

## Deployment Model
- **Local reduced**: Agent API + Postgres (LocalStack optional/deferred) via Compose profiles; defaults are AWS-first. Dev reload available via `docker-compose.dev.yml` with bind mounts; rebuild only for dependency changes.
- **Hybrid dev**: Local services pointing at cloud Postgres/S3 using `.env.dev` and `docker-compose.ec2.yml`.
- **Prod/AWS**: EC2-hosted services via `ENV_FILE=.env.prod ./scripts/deploy_prod_stack.sh`; smoke with `./scripts/prod_smoke_check.sh`.
