# Task 04 — Reduced Scope Docker Compose Deployment

## System Snapshot
- Tasks 01–03 made agent-api runnable without Valkey, queues, or async workers; everything depends only on FastAPI + Postgres + shared data layer packages.
- No container image or Compose profile currently exists for this service; root-level `docker-compose.yml` still references the full architecture (Valkey, workers, SES, etc.).
- `.env.example` and infra docs still describe the production deployment path (GitHub Actions → AWS) rather than the manual demo path we now need.

## What You Inherit
- ReducedScope settings, synchronous ingestion helpers, and CLI commands from Task 03.
- Shared `uv` project configuration, tests, and doc references for metrics/auth.
- Root-level deployment docs (`docs/infrastructure/infrastructure_and_deployment.md`, `DEPLOYMENT.md`) describing the original AWS topology.

## Goal
Provide a local/demo deployment story focused on FastAPI + Postgres: ship a Dockerfile, Compose profile (or standalone `docker-compose.reduced.yml`), seed scripts, and documentation showing how to spin up/tear down the reduced-scope stack without Valkey/SES/queues or GitHub Actions automation.

## Must Read Before Coding
1. `docs/epics/035.md` — Task 3.5.4 scope.
2. `docs/infrastructure/infrastructure_and_deployment.md` §3 — current EC2/Postgres layout + CI/CD assumptions.
3. `README.md` + `QUICKSTART.md` — how the repo currently instructs developers to run services.
4. `services/agent-api/epic-03/subgraph-acceptance.md` — runtime expectations you must preserve when containerizing.
5. `docker-compose.yml` (root) — understand existing services + environment variables.

## Implementation Scope & Files
- Create `services/agent-api/Dockerfile.reduced` (or replace the existing Dockerfile if unused) using a multi-stage build:
  - Stage 1 installs dependencies with `uv sync --all-extras`.
  - Stage 2 copies `services/agent-api` source + `packages/shared_data_layer` (editable install), sets sensible defaults for `REDUCED_SCOPE_ENABLED=1`, `DATABASE_URL=postgresql+asyncpg://...`, etc., and exposes port 8000.
- Author `services/agent-api/docker-compose.reduced.yml` (or add a `reduced` profile to the root compose file) that brings up:
  - `agent-api` container built from the new Dockerfile.
  - `postgres` container with `pgvector` extension enabled + seeded markitdown text fixtures.
  - Optional admin container (`psql` or `alembic`) for running migrations/tests.
  - No Valkey, SES, SQS, or worker containers.
- Add helper scripts: `services/agent-api/scripts/seed_reduced_scope_data.py` (or SQL fixtures) that insert sample documents/chunks/pillar metadata. Hook it into the Compose `command` or README instructions.
- Update `README.md`, `QUICKSTART.md`, and `docs/infrastructure/infrastructure_and_deployment.md` with a “Reduced Scope Demo” section covering prerequisites, `.env` settings, Compose commands (`docker compose -f services/agent-api/docker-compose.reduced.yml up --build`), and manual teardown.
- If `.env.example` lacks the new `REDUCED_SCOPE_*` flags or Postgres credentials, add them.
- Provide a short runbook (`services/agent-api/RUN_TASKS.md` or new `docs/runbooks/reduced_scope_demo.md`) describing how to start/stop the stack, run migrations, seed data, and execute the CLI helpers from Task 03 inside the container.
- Tests/checks: add a CI-friendly smoke test (e.g., `scripts/verify_reduced_scope_compose.sh`) that runs `docker compose config` + `uv run pytest -k reduced_scope_smoke` and mention it in docs.

## Step-by-Step Instructions
1. **Containerize the service**:
   - Build the Dockerfile with `uv` cache layers, `.venv` copy, and a non-root user. Ensure the entrypoint runs `uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2` with `REDUCED_SCOPE_ENABLED=1` by default. Document how to override envs for full mode later.
2. **Compose the reduced stack**:
   - Author the Compose file/profile wiring `agent-api`, `postgres`, and a one-shot `db-init` service that runs `alembic upgrade head && python scripts/seed_reduced_scope_data.py`. Mount local `.env.reduced` for secrets. Provide `make reduced-up`/`make reduced-down` targets or mention `docker compose` commands in the docs.
3. **Document the runbook**:
   - Update infra/README docs describing: required ports, env vars, seeding instructions, how to exec into the container to run Task 03 CLI commands, and how to switch back to the full AWS deployment (list TODO steps: remove `REDUCED_SCOPE_ENABLED`, reintroduce Valkey/SES containers, re-enable GitHub Actions workflows).

## Definition of Done
- Dockerfile + Compose profile exist, build successfully, and start FastAPI + Postgres in reduced scope without Valkey/SES/queues.
- Seed script populates sample markitdown text chunks so `/v1/chat`, `/v1/documents/upload`, and pillar endpoints work immediately after `docker compose up`.
- Documentation/runbook clearly describes setup, commands, and the path to revert to the production deployment later.
- Optional smoke script (or README steps) demonstrates `docker compose config` + minimal pytest run; ensure `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, and `uv run pytest -n auto` still pass locally.
- **Handoff Notes**: Agent must capture image tags, Compose file paths, seed fixtures, and any manual steps left for Task 05 or ops teams.

## Handoff Notes
- List the Docker image name/tag and Compose profile/filename so ops can reference it quickly.
- Note outstanding infra tasks (e.g., TLS, metrics scraping) deferred until after demo.
- Include guidance on where `.env.reduced` lives and which env vars must be overridden when returning to full mode.
