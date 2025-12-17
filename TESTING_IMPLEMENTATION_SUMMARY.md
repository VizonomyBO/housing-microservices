# Testing and Linting Implementation Summary

The quality gates now reflect the cache-free, text-only voyage-context-3 stack across all services.

## Tooling & Automation
- **Root Makefile** runs the canonical gates (`make quality` → format, lint, type-check, tests) across agent-api, ingestion-service, shared_data_layer, auth-service, and user-service using uv-managed virtualenvs.
- **Service Makefiles (auth/user)** now use uv pip for env creation plus ruff, mypy, and pytest targets.
- **uv projects** (agent-api, ingestion-service, shared_data_layer) rely on `uv sync --all-extras` with ruff/ty/pytest defaults.

## Test Coverage Snapshot
- **Agent API**: FastAPI ReAct endpoints (chat/SSE, attachments, documents) with shared data layer fixtures and auth overrides—no cache/graph prerequisites.
- **Ingestion Service**: Markdown chunking + contextual rewrites, voyage-context-3 embedding dimension validation, synchronous pipeline error paths.
- **Shared Data Layer**: Migrations/models/repositories and ingestion smoke (pgvector dimensions sourced from shared config).
- **Auth/User**: JWT issuance/verification and user management; no cache/rate limiter dependencies.

## Smoke & Evals
- Local smoke: `make smoke-local` runs `test-api.sh` against the LocalStack-enabled stack (auth/user/ingestion/agent). Prod smoke via `scripts/prod_smoke_check.sh` with selected env file.
- Eval/tests must use real dependencies; graph RAG, Valkey/rate limiting, and Step Functions flows remain deprecated and are not exercised.

## Defaults & Constraints
- Voyage `voyage-context-3` embeddings (1024-dim default) must align with pgvector storage; mismatches are rejected in ingestion tests.
- Text-only ingestion/retrieval; no reduced-scope/demo toggles or cache layers participate in the quality gates.
