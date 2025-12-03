# Task 02 — Root Compose Implementation & Service Wiring

## System Snapshot
- Task 01 documented the desired multi-service Compose architecture, environment strategy, and LocalStack plan in `docs/infrastructure/root_compose_plan.md`.
- The root `docker-compose.yml` currently targets only a subset of services, while `services/agent-api/docker-compose.reduced.yml` still powers the Reduced Scope demo.
- Each service already has a Dockerfile capable of building locally (Python 3.11/3.13 slim images) but they are not unified under a single Compose network/volume strategy.

## What You Inherit
- The signed-off plan produced by Task 01 (required reading).
- Existing Dockerfiles under `services/*/Dockerfile` and helper scripts (e.g., `services/agent-api/scripts/seed_reduced_scope_data.py`).
- Root-level `.env.example` (to be replaced in Task 03) and service-specific env templates.

## Goal
Refactor the root `docker-compose.yml` into the canonical entrypoint that can spin up **all** microservices plus shared dependencies. The new Compose file must:
- Define build contexts for every service in `services/`.
- Provide shared networks, named volumes, and `depends_on` ordering so services can discover each other via DNS.
- Load environment variables from the root `.env` (to be finalized in Task 03) and expose per-service overrides where necessary.
- Support at least two Compose profiles: `reduced` (FastAPI demo stack) and `full` (all microservices + LocalStack).
- Add a LocalStack service stub (actual wiring handled later) and placeholders for any AWS-dependent infrastructure.
- Remove the now-obsolete `services/agent-api/docker-compose.reduced.yml`.

## Must Read / Inspect Before Coding
1. `docs/infrastructure/root_compose_plan.md` — authoritative design.
2. `docker-compose.yml` (existing root) and `docker-compose.test.yml`.
3. All service Dockerfiles and entrypoints (`services/*/Dockerfile`, `run.py` files).
4. `services/agent-api/scripts/seed_reduced_scope_data.py` and any other init scripts referenced in Compose plan.

## Implementation Scope & Files
- Replace the root `docker-compose.yml` with the architecture defined in Task 01:
  - Services: `agent-api`, `auth-service`, `user-service`, `marker-service`, `swagger-service`, plus shared databases (Postgres with pgvector), LocalStack, and any seed/init jobs.
  - Build contexts should point at the monorepo root and reuse Dockerfiles located under `services/<name>/Dockerfile`.
  - Mount shared source directories (e.g., `./packages`) as bind mounts or COPY-on-build depending on the plan.
  - Define named volumes for Postgres data, LocalStack state, etc.
  - Configure `profiles` (e.g., `reduced`, `full`) so `docker compose --profile reduced up` launches only the demo stack while `--profile full` brings up everything (including LocalStack and auxiliary services).
  - Reference an `env_file: .env` (the real `.env` will be copied from `.env.example` in Task 03).
- Add LocalStack service definition (image, ports, environment) even if the surrounding code is not yet wired to it.
- Move/merge any helper scripts (db init, seeders) that previously lived in `services/agent-api/docker-compose.reduced.yml` into the new root Compose (e.g., a `db-init` service).
- Delete `services/agent-api/docker-compose.reduced.yml` and update any docs/README references to point to the new root Compose (documentation polish happens in Task 05, but remove obvious references now to prevent drift).

## Step-by-Step Instructions
1. **Back up existing Compose assets** (optional) and ensure you are working on a clean git branch.
2. **Implement the new root Compose**:
   - Start from the plan’s service matrix and transcribe each service into `docker-compose.yml`.
   - Use YAML anchors or extension syntax where it reduces duplication (e.g., shared build args, env_file references).
   - Ensure `depends_on` uses `condition: service_healthy` where healthchecks are available (Postgres, LocalStack).
3. **Add helper services/volumes**:
   - Create named volumes for Postgres data and LocalStack state.
   - Add any seed/init containers (e.g., `db-init`) required for Reduced Scope demos.
4. **Delete `services/agent-api/docker-compose.reduced.yml`** and remove any references left in the repo (README updates can wait until Task 05, but dead files should go now).
5. **Validate**:
   - Run `docker compose config` (and `docker compose --profile reduced config`) to ensure syntax + env interpolation succeed.
   - Document any blockers (missing Dockerfiles, build issues) in the task log and plan follow-ups if needed.
6. **Stage changes**: `git add docker-compose.yml services/agent-api/docker-compose.reduced.yml` (deleted) and any related updates.

## Definition of Done
- Root `docker-compose.yml` launches every microservice plus shared infra as defined in Task 01, with working `reduced` and `full` profiles.
- LocalStack service stub exists (even if not yet wired to application code).
- `services/agent-api/docker-compose.reduced.yml` is removed from the repo, and no instructions reference it.
- `docker compose config` and `docker compose --profile reduced config` both succeed without missing-variable errors (document any required env placeholders for Task 03).
- No documentation updates are required yet, but any TODO comments point to Task 05.
