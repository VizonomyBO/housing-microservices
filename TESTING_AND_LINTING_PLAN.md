# Testing and Linting Plan (Revamped Stack)

## Objectives
- Keep all services on the uv-first toolchain with consistent quality gates (`ruff format/check`, `ty`/`mypy`, `pytest -n auto`).
- Ensure tests align with the cache-free, text-only ReAct agent + synchronous ingestion architecture (Voyage `voyage-context-3`, no Valkey/rate limiter/Step Functions).
- Provide clear smoke/eval entry points for local and prod stacks.

## Quality Gates
- Root automation (recommended): `make quality` → runs format, lint, type-check, and tests across agent-api, ingestion-service, shared_data_layer, auth-service, and user-service.
- Service-level:
  - Agent API / Ingestion / Shared Data Layer: `uv run ruff format . && uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`.
  - Auth-Service / User-Service: `make -C services/<service> quality` (uv pip + mypy + pytest).

## Coverage Focus
- Agent API: ReAct agent endpoints (chat/SSE), attachment gating, and shared data layer integration.
- Ingestion Service: MarkItDown → chunk → embed → activation with voyage-context-3 dimensions (default 1024; reject mismatches).
- Shared Data Layer: migrations/models/repositories with pgvector dimensions, ingestion smoke (`tests/test_end_to_end_ingestion.py` opt-in).
- Auth/User: JWT issuance/verification and user CRUD flows (no cache/rate limiter dependencies).

## Smoke/Evals
- Local smoke: `make smoke-local` (auth/user/ingestion/agent + LocalStack mocks; requires API keys for agent health).
- Prod smoke: `ENV_FILE="$(scripts/use_env.sh prod)" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`.
- Evals/tests must run against real dependencies—no stubs for cache/graph/Step Functions.

## Notes
- Text-only ingestion/retrieval; voyage-context-3 embeddings are length-normalized and must match the pgvector column dimension.
- Graph RAG and reduced-scope/demo profiles are deprecated; keep any remaining references documented but not executed in tests.
