# Root Compose Modernization Plan (Task 01)

## 1. Objectives & Deployment Modes
- Unify every microservice under the root `docker-compose.yml` so `docker compose up` becomes the single entrypoint.
- Support two runtime profiles:
  - `full`: boots Postgres + auth-service + user-service + swagger-service + agent-api + marker-service + shared dependencies (Valkey, LocalStack, telemetry exporters).
  - `reduced`: limits startup to agent-api, its `db-init` helper, and Postgres with the Epic 3.5 feature flags to keep text-only, no-Valkey mode.
- Keep parity with the legacy reduced-scope experience (seed scripts, `uv` runtime, pgvector) while paving the path to retire the old service-scoped reduced Compose file.

## 2. Service & Dependency Inventory
| Component | Runtime / Image | Ports | Build Context | Critical Dependencies | Notes |
| --- | --- | --- | --- | --- | --- |
| `postgres` | `pgvector/pg16` | Host `POSTGRES_PORT`/5432 | root (scripts/init-databases.sh) | Persists `housing`, `auth_db`, `agent_reduced` schemas | Needs volume split so reduced demo can wipe its data without affecting primary tables.
| `db-init` | `services/agent-api/Dockerfile.reduced` (init profile) | n/a | repo root | Depends on Postgres healthy; runs Alembic + `scripts/seed_reduced_scope_data.py --if-empty` | Should run inside reduced profile and optional admin profile for reseeding.
| `agent-api` | Python 3.13 + FastAPI + LangGraph (`uv`-managed) | 8000 | repo root → `services/agent-api` | async Postgres (`postgresql+asyncpg`), shared data layer package | Needs REDUCED vs FULL flags to control Valkey, workers, and AWS usage.
| `auth-service` | Python 3.11 Flask | 5000 (host 5001) | `services/auth-service` | Postgres `auth_db`, Argon2/libpq packages | Already exposes health endpoint for Compose healthcheck; reuse.
| `user-service` | Python 3.11 Flask | 5001 (host 5002) | `services/user-service` | Depends on auth-service API + Postgres `auth_db` | Share JWT + CORS envs with auth-service.
| `swagger-service` | Node 20 | 3000 | `services/swagger-service` | Depends on auth-service + user-service HTTP endpoints | Provide optional dev profile for hot reload stack.
| `marker-service` | Python 3.12 FastAPI | 8004 | `services/marker-service` | S3 via boto3, OpenAI API | Requires LocalStack endpoints for S3/EventBridge in local mode.
| `localstack` | `localstack/localstack` | 4566 edge | root (new) | AWS emulation for S3, EventBridge, SES, SQS | Toggle through `USE_LOCALSTACK` and route SDKs via `localhost.localstack.cloud`/shared network.¹
| `valkey` (future) | `valkey/valkey` or AWS serverless proxy | 6379 | root (new) | Agent API caching, rate limiting | Keep container gated behind `full` profile until queues/worker tasks return.
| `otel-collector` (optional) | OpenTelemetry collector | 4317 | root (new) | Receives traces/metrics from services | Helps keep architecture parity with production monitoring.

## 3. Proposed Compose Structure
### 3.1 File Layout
- Keep a single `docker-compose.yml` at repo root that defines every service + dependency.
- Add `docker-compose.override.yml` (git-ignored) for personal overrides.
- Provide profile-aware helper targets in `Makefile` (`make up-full`, `make up-reduced`, `make up-localstack`).

### 3.2 Profiles
| Profile | Purpose | Services |
| --- | --- | --- |
| `default` | Postgres + auth + user + swagger (maintains todays behavior). | `postgres`, `auth-service`, `user-service`, `swagger-service`.
| `agent-api` | Reduced Epic 3.5 demo stack. | `postgres`, `db-init`, `agent-api` (+ optional `db-shell`).
| `full` | All services plus LocalStack, Valkey, observability. | `default` services + `agent-api`, `marker-service`, `valkey`, `localstack`, `otel-collector`.
| `aws-mock` | Enables LocalStack without the rest of `full`. | `localstack` (reusable for CI smoke tests).
| `ops` | Long-running helpers (db-shell, seed-only jobs). | `db-shell`, `db-init` reruns, migration runners.

Compose consumers can activate combinations via `COMPOSE_PROFILES=full,ops docker compose up` as documented in Dockers service profile guide.¹

### 3.3 Networking & Volumes
- Networks
  - `microservices-net`: bridge network for service-to-service RPC (default for all containers).
  - `public-edge`: optional network for exposing swagger-service via reverse proxy in future tasks.
  - `localstack-net`: attach `localstack` + any AWS clients that need DNS-based hostname mapping.
- Volumes
  - `postgres_data`: shared Postgres storage.
  - `agent_pg_data`: optional named volume for reduced-profile Postgres so demos can be reset without nuking `postgres_data`.
  - `localstack_data`: caches emulated AWS state.
  - `shared_cache`: reserved for Valkey when reinstated.

### 3.4 Dependency Graph Highlights
- `auth-service` and `user-service` depend on `postgres` + each other (JWT + `/auth` endpoints).
- `swagger-service` depends on `auth-service` + `user-service` HTTP health.
- `marker-service` depends on `auth-service` (for tokens) and `localstack`/AWS for document storage.
- `agent-api` depends on `postgres`, optionally `valkey`, and AWS services (S3/EventBridge) once the full pipeline is restored.
- `db-init` depends on `postgres` and `packages/shared_data_layer` migrations.

### 3.5 Operational Commands
- `docker compose --profile full config` (CI guard) and `docker compose --profile agent-api up agent-api db-init` for demo mode.
- Extend `services/agent-api/scripts/verify_reduced_scope_compose.sh` to call the new root compose file with `COMPOSE_PROFILES=agent-api`.

## 4. Environment Variable Strategy
1. **Global `.env` (root):** authoritative source for shared ports, Postgres creds, JWT secrets, AWS creds, `SERVICE_MODE`, `USE_LOCALSTACK`, `LOCALSTACK_EDGE_PORT`. Compose interpolation precedence (shell > working-dir `.env` > `--env-file`) needs documenting so automation doesnt silently override values.²
2. **Service-level env files:** keep `services/<service>/.env.example` for any additional settings. Compose can load them via per-service `env_file` entries, but secrets should still flow from the root `.env` or Docker secrets.
3. **Profiles + toggles:**
   - `SERVICE_MODE=reduced|full` toggles runtime flags in agent-api (Valkey/queues on vs off).
   - `USE_LOCALSTACK=1|0` determines whether services point to `http://localstack:4566` vs AWS endpoints.
   - `COMPOSE_PROFILES` default to `default`; docs should show `COMPOSE_PROFILES=agent-api` for demos.
4. **Secrets handling:**
   - Encourage `.env.local` (gitignored) for developer overrides.
   - Use Docker secrets or AWS Secrets Manager in production; Compose plan should anticipate migrating to `env_file: ./env/.aws.localstack` for CI toggles.
5. **Matrix documentation:** root plan should publish a table that lists each variable, default, consumer services, and whether it belongs in global `.env`, profile-specific env, or secret store. (Will be produced during Task 03.)

### 4.1 Canonical `.env.example`
- `env.example` at the repo root is now the single source of truth. Copy it to `.env`, then override sensitive values either directly or via a gitignored `.env.local` before running Compose.
- **Compose & profiles**: `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES`, `STACK_PROFILE`, `SERVICE_MODE`, and `REDUCED_SCOPE_ENABLED` describe which runtime (reduced/full) is active so helper scripts can map them to Docker profiles.
- **Database & credentials**: `POSTGRES_*`, `AUTH_DB`, `AGENT_API_DB*`, and `DATABASE_URL` match the variables consumed by `docker-compose.yml` and `scripts/init-databases.sh`, keeping auth + agent schemas consistent.
- **Auth/JWT + service ports**: `JWT_*`, `SECRET_KEY`, `CORS_ORIGINS`, and the host port overrides (`POSTGRES_PORT`, `AGENT_API_PORT`, `AUTH_SERVICE_PORT`, `USER_SERVICE_PORT`, `SWAGGER_SERVICE_PORT`, `MARKER_SERVICE_PORT`) now live in one place instead of service-specific templates.
- **Agent API flags & metrics**: `SERVICE_NAME`, `METRICS_*`, and every `REDUCED_SCOPE_*` flag bind directly to `src/agent_api/settings.py`, preventing drift between env parsing and the Compose defaults.
- **AWS/LocalStack**: `USE_LOCALSTACK`, `LOCALSTACK_HOST`, `LOCALSTACK_EDGE_PORT`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL`, plus `RAW_DOCUMENTS_BUCKET`/`PROCESSED_BUCKET` capture both reduced-mode LocalStack usage and the eventual real AWS endpoints.
- **Cache/observability**: `VALKEY_*` and `OTEL_COLLECTOR_*` are grouped with descriptive defaults so re-enabling Valkey/OTel in the full profile only requires flipping envs, not editing Compose.
- **Shared service URLs**: `AUTH_SERVICE_URL`, `USER_SERVICE_URL`, and `ACCOUNT_SERVICE_URL` are interpolated via `${VAR:-default}` inside Compose instead of being hard-coded, keeping swagger-service and user-service aligned with whichever ports the developer picked.

## 5. LocalStack Integration
- Add a `localstack` service (image `localstack/localstack:latest`) with exposed `4566` edge port, environment variables `SERVICES=s3,sqs,sns,events,secretsmanager`, and mount for persistence (`localstack_data`).
- Tie the service to `aws-mock` and `full` profiles; automatically start when `USE_LOCALSTACK=1`.
- Provide shared env variables for AWS clients:
  - `AWS_REGION` default `us-east-1`.
  - `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` use dummy values when `USE_LOCALSTACK=1`.
  - `LOCALSTACK_HOST=localstack`, `LOCALSTACK_EDGE_PORT=4566`, `AWS_ENDPOINT_URL=http://localstack:4566` (or `http://localhost.localstack.cloud:4566` for host tools).¹
- Services that currently touch AWS:
  - `marker-service`: S3 uploads via boto3 → set `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
  - Future restoration of ingestion Lambdas/agent workers: plan placeholders for EventBridge/S3/SQS.
- Networking considerations: attach application services and LocalStack to the same user-defined bridge so DNS `localstack` resolves correctly.¹

## 6. Migration Steps Away from `docker-compose.reduced.yml`
1. **Port reduced assets:**
   - Move `db-init` service definition (including `profiles: ["init", "agent-api"]`, env files, `uv run alembic ...` command) into the root compose file under the `agent-api` profile.
   - Mount `services/agent-api/scripts/initdb` into Postgres via `docker-compose.yml` so the seeding SQL stays available.
2. **Env consolidation:**
   - Merge `services/agent-api/.env.reduced.example` settings into the root `env.example` and new `env.agent-api.example` file so there is a single source of truth.
3. **Docs/runbooks:**
   - Update `docs/runbooks/reduced_scope_demo.md` to call the root compose file with `COMPOSE_PROFILES=agent-api`.
   - Remove references to `docker-compose.reduced.yml` from README/QUICKSTART once Task 02 implements the stack.
4. **Deletion checklist:**
   - After Task 02 verifies parity, delete the deprecated service-level reduced Compose file and associated scripts that duplicated root behavior. (Completed December 2025, note retained here for historical context.)
   - Preserve `scripts/verify_reduced_scope_compose.sh` by pointing it to the root compose file.
5. **CI adjustments:** ensure GitHub workflows or future `uv` scripts call `docker compose --profile agent-api config` as part of linting.

## 7. Open Questions & Risks
- `agent-api` lacks a non-reduced Dockerfile; need confirmation whether reduced Dockerfile should be reused for full mode or if a production Dockerfile lives elsewhere.
- Marker-service currently depends on AWS S3 + OpenAI but isnt wired into any Compose stack; confirm runtime secrets (OpenAI API key) and whether LocalStack should also mock EventBridge for ingestion.
- Multi-DB Postgres: root compose currently runs a single instance for both `housing` and `auth_db`. Need to validate whether `pgvector` extensions required by agent-api conflict with existing 15/16 images.
- Resource usage: running `full` profile locally will require >6 GB RAM (Node + multiple Python services + LocalStack). Document fallbacks for lower-end machines (start `reduced` + `swagger` only).
- Secrets governance: once LocalStack toggles land, need a plan for storing AWS credentials for prod vs dev to avoid leaking real keys into `.env`.

## 8. Testing & Validation Approach
- `docker compose --profile agent-api config` (lint), `docker compose --profile agent-api up --build agent-api db-init` (demo smoke), `docker compose --profile full up marker-service localstack valkey` (AWS mock smoke).
- Reuse existing scripts:
  - `services/agent-api/scripts/verify_reduced_scope_compose.sh` should wrap the root compose file.
  - Future Task 02 should add a root-level `scripts/verify_root_compose.sh` that runs `docker compose config` + targeted pytest suites.
- Document how to tail logs per service via `docker compose logs -f agent-api` and `Makefile` shortcuts once new profiles exist.

---
¹ Docker Docs, "Use service profiles". <https://docs.docker.com/compose/how-tos/profiles/>
² Docker Docs, "Interpolation" (environment variable precedence). <https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/>
³ LocalStack Docs, "Accessing LocalStack via the endpoint URL". <https://docs.localstack.cloud/aws/capabilities/networking/accessing-endpoint-url/>
