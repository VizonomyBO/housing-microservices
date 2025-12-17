# Testing and Quality Assurance Guide

The stack runs a FastAPI ReAct agent, a synchronous FastAPI ingestion service, Flask-based auth/user services, and the shared data layer. Everything is uv-first, text-only, and uses Voyage `voyage-context-3` embeddings (1024-dim by default) with no Valkey/cache or Step Functions assumptions.

## Environment & Dependencies
- Install `uv` (Python 3.13). Select envs with `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a` when you need real services.
- Sync all service environments: `make sync` (creates `.venv` in each service and installs dev/test deps).
- Sync a single uv-managed service: `cd services/agent-api && uv venv --python 3.13 .venv && uv sync --all-extras` (same for `services/ingestion-service`, `packages/shared_data_layer`).
- Sync a single Flask service: `make -C services/auth-service venv` or `make -C services/user-service venv`.

## Core Quality Gates (root `Makefile`)
Run from repo root after syncing deps:

```bash
make format       # ruff format + autofix across services
make lint         # ruff check
make type-check   # ty for uv projects; mypy for auth/user
make test         # pytest -n auto across services
make quality      # format → lint → type-check → tests
```

## Service-Specific Shortcuts
- Agent API / Ingestion / Shared Data Layer (uv-managed):
  - `uv run ruff format .`
  - `uv run ruff check --fix .`
  - `uv run ty check .`
  - `uv run pytest -n auto`
- Auth-Service / User-Service (uv pip + .venv):
  - `make -C services/auth-service quality`
  - `make -C services/user-service quality`

## Smoke & Integration
- Local smoke (auth/user/ingestion/agent + LocalStack): `make smoke-local` (uses `test-api.sh`; requires relevant API keys for the agent health check).
- Prod/AWS smoke: `ENV_FILE="$(scripts/use_env.sh prod)" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`

## Notes & Defaults
- Text-only ingestion and retrieval; voyage-context-3 embeddings (default 1024-dim) must match the pgvector column dimension.
- No Valkey/rate-limiter/Step Functions/reduced-scope flows. Tests should not expect cache layers or graph planners.
- Keep test data unique for ingestion smokes; LocalStack is only used for AWS mocks in dev.
