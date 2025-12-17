# System Architecture

## Overview
The platform is a text-only, ingestion-first RAG stack:
- **Ingestion service (FastAPI)** handles uploads end-to-end (MarkItDown → contextual chunking → Voyage `voyage-context-3` embeddings → pgvector activation). Agent API never ingests directly.
- **Agent API (FastAPI ReAct)** runs a tool-based loop with hybrid retrieval (BM25 + pgvector) reranked by `rerank-2.5`, attachment/status helpers, rerank utilities (HyDE/HyPE, contextual headers), and a Pyodide sandbox tool for computations/tabular work (Wasm, no filesystem; install extras via `micropip`/`httpx`).
- **Auth/User services (Flask)** provide JWT issuance/validation and user management backed by `auth_db`.
- **Shared data layer** (`packages/shared_data_layer`) owns all models/repos; graph/workflow tables persist but are **deprecated** and should remain nullable/documented only.
- **Postgres 16 + pgvector** stores retrieval data (`housing`) and auth data (`auth_db`). LocalStack supplies AWS mocks for dev; production bypasses it.

```mermaid
flowchart LR
    Client -->|JWT login| Auth[Auth Service]
    Client -->|users| User[User Service]
    Client -->|chat/upload| Agent[Agent API (FastAPI ReAct)]
    Agent -->|proxy upload| Ingest[Ingestion Service]
    Agent -->|retrieval (BM25+vector)| HousingDB[(Postgres 16 + pgvector<br/>housing DB)]
    Ingest --> HousingDB
    Auth --> AuthDB[(Postgres 16<br/>auth_db)]
    User --> AuthDB
    Agent -->|Pyodide sandbox| Sandbox[Pyodide (Wasm, no FS)]
    LocalStack[(LocalStack dev)] -.-> Agent
```

## Components
- **Agent API**
  - ReAct agent built with LangChain `create_agent` + LangGraph checkpoints.
  - Tools: hybrid retrieval (BM25 + pgvector with voyage-context-3 embeddings), rerank-2.5 utility, attachment/status helpers, document listing/activation, Pyodide code executor.
  - Responses require per-fact `[c#]` citations; UUID `thread_id` enforces ownership. No cache/rate-limiter dependency; fail fast when Voyage/OpenAI keys are missing.
- **Ingestion Service**
  - Single synchronous path: `POST /v1/documents/upload` returns an HMAC-signed form upload; service runs MarkItDown → contextual chunking → Voyage embeddings (1024-d default; 256/512/2048 supported when DB matches) → pgvector insert → activation.
  - Allowed `source_type`: pdf, docx, doc, txt, md, html, json. Output dimensions are length-normalized (cosine/dot equivalent).
- **Auth/User Services**
  - Flask 3.x apps using Argon2 hashing and PyJWT; JWTs consumed by agent-api and ingestion-service. Keep schemas isolated in `auth_db`.
- **Shared Data Layer**
  - Authoritative SQLAlchemy models/repos. Graph/workflow tables remain for backward compatibility but are deprecated; mark unused relations nullable and document them rather than deleting.

## Data flow
1. **Upload**: Client hits Agent API upload proxy → ingestion-service `/v1/documents/upload` (HMAC form) → binary POST to ingestion-service → synchronous pipeline activates doc.
2. **Attach**: Client creates conversation and attaches doc IDs; Agent API blocks chat until docs are `active`.
3. **Chat**: ReAct loop runs retrieval (BM25 + pgvector) → fusion → rerank-2.5 → Pyodide/tool calls as needed → grounded answer with `[c#]` citations.
4. **Persistence**: Conversations, checkpoints, citations, and chunks live in `housing`; auth data lives in `auth_db`.

## Environments
- **Local**: Docker Compose + LocalStack. Command: `docker compose --env-file "$env_file" up -d --build` → `./test-api.sh`.
- **Hybrid**: Local services with remote data plane via `docker-compose.ec2.yml`.
- **Prod**: EC2 deploy via `scripts/deploy_stack.sh --mode services-only|full-redeploy`; smoke with `scripts/prod_smoke_check.sh` (ingest → activate → attach → chat).

## Deprecations (historical only)
- Removed from active workflows: Step Functions/Lambda ingestion, graph RAG planners, Valkey cache/rate limiter, reduced-scope/demo modes, telemetry extras, Swagger aggregator.
- Legacy epics/interfaces remain archived for history; new work must use the ingestion-first, Voyage `voyage-context-3` + `rerank-2.5` stack described above.
