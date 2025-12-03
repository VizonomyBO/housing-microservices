# Reduced Scope Demo Runbook

This runbook explains how to launch the Agent API + Postgres demo stack for Epic 3.5 using only FastAPI, LangGraph, and the shared data layer. The flow keeps Valkey, SES, SQS, and GitHub Actions disabled while preserving the full production architecture behind feature flags.

## Prerequisites
- Docker 25.x+ with Compose V2 (`docker compose` CLI).
- Python 3.13-compatible host (only required for running `uv` commands outside containers).
- Access to the repo root (`housing-microservices`).

## Environment Files
1. Copy `services/agent-api/.env.reduced.example` to `.env.reduced` inside the same directory.
2. Adjust secrets as needed:
   - `AGENT_API_DB_PASSWORD` — Postgres password for the demo database.
   - `DATABASE_URL` — Async SQLAlchemy URL (default uses `postgresql+asyncpg`).
   - `REDUCED_SCOPE_*` flags — leave enabled for the demo; flip to `0` only when re-enabling Valkey/queues.
3. Root-level `env.example` now documents the same variables so CI/CD and manual runs share the same defaults.

## Bringing Up the Stack
```bash
cd services/agent-api
./scripts/verify_reduced_scope_compose.sh   # optional but recommended
COMPOSE_FILE=docker-compose.reduced.yml
DATABASE_URL=postgresql+asyncpg://agent_api:agent_api_pass@postgres:5432/agent_reduced \
  docker compose -f "$COMPOSE_FILE" up --build
```
- `postgres` exposes port 5434 on the host (configurable via `AGENT_API_DB_PORT`).
- `db-init` runs `alembic upgrade head` followed by `python scripts/seed_reduced_scope_data.py --if-empty`.
- `agent-api` container listens on `${AGENT_API_PORT:-8000}` with `REDUCED_SCOPE_ENABLED=1`.

### Seeding & Admin Actions
- Seed script runs automatically, but you can re-run it:
  ```bash
  docker compose -f services/agent-api/docker-compose.reduced.yml run --rm agent-api \
    uv run python scripts/seed_reduced_scope_data.py --force
  ```
- `db-shell` profile exposes a long-running Postgres container for manual psql access:
  ```bash
  docker compose -f services/agent-api/docker-compose.reduced.yml run --rm db-shell psql \
    -h postgres -U agent_api -d agent_reduced
  ```

### Running CLI Helpers
Exec into the API container to run the reduced-scope CLI from Task 03:
```bash
docker compose -f services/agent-api/docker-compose.reduced.yml exec agent-api \
  uv run agent-runtime generate-pillars --country-code USA
```

## Teardown
```bash
docker compose -f services/agent-api/docker-compose.reduced.yml down
# Remove volumes (including Postgres data)
docker compose -f services/agent-api/docker-compose.reduced.yml down -v
```

## Smoke Verification
- `services/agent-api/scripts/verify_reduced_scope_compose.sh` validates the Compose file and runs `pytest -k reduced_scope_smoke`.
- CI jobs can call the script directly to guard against regressions without bringing containers up.

## Reverting to Full Architecture (Post-demo)
1. Set `REDUCED_SCOPE_ENABLED=0` and restore Valkey/SQS configuration in `.env` files.
2. Switch deployment pipelines back to `docs/infrastructure/infrastructure_and_deployment.md` AWS flow (re-enable GitHub Actions workflows, Terraform Valkey/SES modules, worker ASGs).
3. Reintroduce Valkey/SES containers into the root `docker-compose.yml` or an extended profile if a local cache is required for testing before production.
4. Remove/disable the `db-init` helper once CI/CD handles migrations and seeding again.

Document outstanding infra follow-ups in `services/agent-api/epic-035/tasks/task-05-auth-notification-fallback.md` before leaving the reduced-scope mode.
