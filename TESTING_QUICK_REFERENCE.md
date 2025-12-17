# Testing Quick Reference

## Setup
- Install `uv` (Python 3.13).
- Sync deps: `make sync` (creates `.venv` for agent-api, ingestion-service, shared_data_layer, auth-service, user-service).

## Core Commands (repo root)
```bash
make format       # ruff format + autofix across services
make lint         # ruff check across services
make type-check   # ty (uv projects) + mypy (auth/user)
make test         # pytest -n auto everywhere
make quality      # run all of the above
make smoke-local  # local auth/user/ingestion/agent smoke via test-api.sh
```

## Service Shortcuts
- Agent API / Ingestion / Shared Data Layer:
  - `uv venv --python 3.13 .venv && uv sync --all-extras`
  - `uv run ruff format . && uv run ruff check --fix .`
  - `uv run ty check .`
  - `uv run pytest -n auto`
- Auth-Service / User-Service:
  - `make -C services/auth-service quality`
  - `make -C services/user-service quality`

## Test Locations
- Agent API: `services/agent-api/tests/` (chat, documents, attachments; async FastAPI + shared data layer fixtures)
- Ingestion Service: `services/ingestion-service/tests/` (chunking + voyage-context-3 dimension guards)
- Shared Data Layer: `packages/shared_data_layer/tests/` (models, migrations, repositories, ingestion smoke)
- Auth/User: `services/auth-service/tests/`, `services/user-service/tests/`

## Defaults
- Text-only ingestion/retrieval with Voyage `voyage-context-3` (1024-dim).
- No Valkey/cache/rate limiter/Step Functions/reduced-scope profiles in tests.
