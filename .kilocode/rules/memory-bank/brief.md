# Project Brief: Housing Microservices Platform

## Overview
A LangGraph-powered Agent API with a FastAPI ingestion service on EC2, Flask-based auth/user microservices, and an optional Swagger aggregator. Docker Compose drives local and hybrid workflows, with AWS EC2 + Postgres as the primary production target. The shared data layer lives in `packages/shared_data_layer`, and Python tooling is managed with `uv` on Python 3.13.

## Key Components
- **Agent API (FastAPI + LangGraph)**: Chat/SSE, attachments, hybrid retrieval, and citation-rich responses. `/v1/documents/upload` now proxies to the ingestion service (no inline ingestion).
- **Ingestion Service (FastAPI on EC2)**: MarkItDown → chunk → embed (Voyage) → index (pgvector) and activate documents; replaces the old Lambda/S3 flow and is the only upload path.
- **Auth Service (Flask)**: Issues and validates JWTs; backed by `auth_db`.
- **User Service (Flask)**: User management; depends on auth-service.
- **Swagger Service (Node/Express)**: Optional aggregated API docs; currently not deployed.
- **PostgreSQL 16 + pgvector**: Two logical databases—`housing` (Agent API/shared data layer) and `auth_db` (auth/user).
- **Docker Compose**: Profiles for reduced local demo, hybrid dev, and prod/EC2 workflows.

## Technology Stack
- **Python 3.13 + uv** for Agent API and ingestion; FastAPI, LangGraph, Pydantic v2, SQLAlchemy 2.x, Voyage embeddings/rerankers.
- **Flask 3.x** for auth/user with Argon2 hashing, PyJWT, Flask-Limiter.
- **Node.js 20/TypeScript 5** for the optional Swagger aggregator.
- **PostgreSQL 16 + pgvector**, asyncpg/psycopg drivers.

## Features
- **Retrieval & QA**: Hybrid BM25 + vector search with Voyage embeddings + reranker (required), HyDE-style rewrites, numeric-aware citation scoring, and per-fact `[c#]` footnotes.
- **Security**: Argon2id hashing, JWT rotation, rate limiting, CORS/configurable origins, attachment safety (documents gated until ingestion active).
- **Fail-fast dependencies**: Voyage, Valkey, and rate limiting are required by default; bypass flags are test-only.
- **Observability**: Health endpoints, structured logging, and smoke run artifacts via `scripts/prod_smoke_check.sh`.
- **Patch Deploys**: Hot-patch Python services on EC2 via `scp` + `docker cp` + compose restart (see AGENTS.md §7).

## Deployment & Environments
- **Local (LocalStack)**: Reduced profile for Agent API + Postgres; LocalStack is currently deferred/broken and will be revisited later. Defaults are AWS-first.
- **Hybrid Dev**: Local services pointing at cloud Postgres/S3 via `.env.dev` and `docker-compose.ec2.yml`.
- **Production**: EC2-hosted services with `ENV_FILE=.env.prod ./scripts/deploy_prod_stack.sh` and `./scripts/prod_smoke_check.sh`.

## Quick Start
1. `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source \"$env_file\" && set +a`
2. Local reduced profile: `COMPOSE_PROFILES=reduced,ops docker compose --env-file \"$env_file\" up -d --build`
3. Hybrid dev: `docker compose --env-file \"$env_file\" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`
4. Prod smoke: `ENV_FILE=\"$env_file\" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`

## Testing
- Preferred quality gates (Agent API): `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`.
- `test-api.sh` provides manual endpoint coverage; AWS smoke runs documented under `notes/aws_step9_status.md`.

## Documentation
Key references under `docs/`: system/agent architecture, schema & persistence, testing/evals (LLM quality hardening), and reduced-scope demos.

## Project Status
Actively validating the FastAPI ingestion + Agent API path on AWS (Step 9); LocalStack verification is deferred. Swagger UI remains disabled. Continue using real retrieval/ingestion (no stubs) and keep plan/tracker files in place for the ongoing ingestion verification work.
