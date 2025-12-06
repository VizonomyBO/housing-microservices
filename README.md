# Housing Microservices Platform

A polyglot demo platform that pairs the FastAPI-based Agent API (LangGraph gateway) with the legacy authentication, user, and swagger services. The repo now ships a single root `docker-compose.yml` that can start either a reduced Agent API demo or the full stack with LocalStack-backed AWS emulation.

> Note: `marker-service` has been removed (legacy). It is no longer built or shipped; ignore it in all flows unless explicitly resurrecting historical behavior.
> Rule of thumb: ignore unused/legacy services unless a task explicitly asks for them.

## Quick links (AWS-first)
- Production setup, curl walkthrough, and frontend endpoint reference: `docs/runbooks/prod_setup.md`
- Idempotent prod deploy (Terraform + EC2 compose): `scripts/deploy_prod_stack.sh`
- AWS smoke helper (uploads policy/ledger/KPI PDFs via ingestion service): `ENV_FILE=.env.active bash scripts/prod_smoke_check.sh` (see runbook §6)

## Service Inventory
| Service | Language | Host Port | Profiles | Notes |
| --- | --- | --- | --- | --- |
| `postgres` | pgvector 16 | `${POSTGRES_PORT:-5432}` | default | Shared database for every service plus the reduced agent schema.
| `db-init` | Python/uv | n/a | `reduced`, `full`, `ops` | Runs Alembic migrations + `scripts/seed_reduced_scope_data.py --if-empty`.
| `agent-api` | FastAPI + LangGraph | `${AGENT_API_PORT:-8000}` | `reduced`, `full` | Text-only demo when `SERVICE_MODE=reduced`; reconnects to Valkey/AWS once flags flip.
| `auth-service` | Flask | `${AUTH_SERVICE_PORT:-5001}` | default | Issues JWTs for the UI + downstream services.
| `user-service` | Flask | `${USER_SERVICE_PORT:-5002}` | default | Depends on auth-service for token validation.
| `swagger-service` | Node/Express | `${SWAGGER_SERVICE_PORT:-3000}` | default | Aggregates OpenAPI docs for every public service.
| `localstack` | LocalStack | `${LOCALSTACK_EDGE_PORT:-4566}` | default, `agent-api`, `full`, `aws-mock` | Emulates AWS endpoints when `USE_LOCALSTACK=1`.
| `valkey` | Valkey 7 | `${VALKEY_PORT:-6379}` | `full` | Cache/rate-limit placeholder until the queue workers return.
| `otel-collector` | OpenTelemetry | `${OTEL_COLLECTOR_GRPC_PORT:-4317}` | `full` | Optional traces/metrics collector.
| `db-shell` | Postgres client | n/a | `ops`, `reduced`, `full` | Long-lived psql shell for ad-hoc queries.

## Prerequisites
- Docker Desktop 25.x (or Engine 25.x) with Compose V2 (`docker compose`).
- Git + bash-compatible shell (scripts assume POSIX shell semantics).
- Optional: [uv](https://github.com/astral-sh/uv) to run scripts/tests without leaving the virtualenv.

## 1. Clone & Seed Config
```bash
git clone <repo-url>
cd housing-microservices
cp env.example .env        # never commit secrets
```
Update `.env` with non-default passwords, JWT secrets, and any AWS credentials needed for full-mode testing. Use `.env.local` for personal overrides.

## 2. Pick a Stack Profile
`STACK_PROFILE` mirrors the documentation narrative, while Compose profiles control which containers run.

| Use Case | STACK_PROFILE | Compose Flag | What Starts |
| --- | --- | --- | --- |
| Reduced Agent API demo | `reduced` | `docker compose --profile reduced up agent-api` | `postgres`, `db-init`, `agent-api`, `db-shell`, `localstack` (for S3 mocks).
| Full platform | `full` | `docker compose --profile full up` | Everything above plus auth-service, user-service, swagger-service, valkey, otel-collector. (Marker-service removed/legacy.) |
| Default legacy stack | `reduced` or `full` | `docker compose up` | `postgres`, auth-service, user-service, swagger-service, localstack.

You can also set `COMPOSE_PROFILES` in `.env` or your shell (e.g., `COMPOSE_PROFILES=reduced,ops`). Compose always includes services without an explicit `profiles` entry (`postgres`, auth-service, user-service, swagger-service).

## 3. Launch the Stack
### Reduced (Epic 3.5 demo)
```bash
STACK_PROFILE=reduced \
COMPOSE_PROFILES=reduced \
  docker compose --profile reduced up --build agent-api
```
- `db-init` waits for Postgres, runs Alembic migrations, then seeds via `services/agent-api/scripts/seed_reduced_scope_data.py --if-empty`.
- The Agent API starts with `REDUCED_SCOPE_*` flags enabled, so `/v1/chat`, `/v1/documents/upload`, and pillar routes all run without Valkey.
- Visit `http://localhost:${AGENT_API_PORT:-8000}/docs` for FastAPI, or see service URLs below.

### Full stack + LocalStack
```bash
STACK_PROFILE=full \
COMPOSE_PROFILES=full \
  docker compose --profile full up --build
```
- Brings up every service, LocalStack, Valkey, and optional telemetry.
- Expect the first build to take several minutes because each service image builds from source.
- Tail logs service-by-service (`docker compose logs -f agent-api`, `docker compose logs -f localstack`).

### Stopping & Cleaning Up
```bash
docker compose down              # stop containers, keep volumes
docker compose down -v           # wipes Postgres/LocalStack data
docker compose --profile full down -v  # clean specific profile runs
docker compose --profile reduced down -v --remove-orphans  # force-remove lingering reduced-stack networks
```

## 4. Verify & Smoke Test
- Validate Compose file + reduced profile: `services/agent-api/scripts/verify_reduced_scope_compose.sh` (runs `docker compose --profile reduced config` + `pytest -k reduced_scope_smoke`).
- Quick config sanity check for the full stack: `docker compose --profile full config`.
- Hit health endpoints once containers are healthy:
  - Swagger UI: `http://localhost:${SWAGGER_SERVICE_PORT:-3000}`
  - Agent API health: `curl http://localhost:${AGENT_API_PORT:-8000}/health`
  - Auth service: `curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health`
  - LocalStack status: `curl http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health`

### One-command reduced E2E smoke
Use the new wrapper if you want the reduced stack, health probes, and CLI automation to run with a single command from the repo root:

```bash
make reduced-e2e-smoke            # optionally pass ARGS="--skip-pillars"
```

The target calls `services/agent-api/scripts/run_reduced_e2e_compose.sh`, which copies `.env` from `env.example` when missing, starts the reduced + LocalStack compose profile, waits for `/health` + `/v1/health`, runs the smoke CLI inside the `agent-api` container, then tears everything down. Set `KEEP_STACK=1` to leave containers running or `ARGS="--timeout-seconds 45"` to forward options to the CLI. Logs stream to `services/agent-api/logs/task_04/codex.log` for later review.

### Inspect SQL trace outputs
- `scripts/prod_smoke_check.sh` now writes `requires_sql`, `sql_queries`, `sql_row_count`, and `table_results` for each prompt in `prod_sample_run.json`. Quantitative prompts should show `requires_sql: true`, a non-empty SQL list, row counts, and preview rows that match the cited KPI values.
- The `/v1/chat` `done` payloads mirror the same fields (including `sql_row_count`). When you run the reduced E2E CLI, the resulting `PromptRunResult` entries will embed the SQL query string and executor row count for auditing.
- Use these fields (plus the `[SQL_RESULT]` citation injected by the answer synthesizer) to prove every numeric answer was grounded in the Polars executor rather than free-form arithmetic.

## 5. Seed & Admin Utilities
- **Automatic seeding** happens every time `db-init` runs.
- Manually reseed:
  ```bash
  docker compose run --rm db-init
  ```
- Run Agent API CLI helpers (pillar generation, ingestion, etc.):
  ```bash
  docker compose --profile reduced exec agent-api \
    uv run agent_api.cli --help
  ```
- Connect to Postgres with `db-shell`:
  ```bash
  docker compose --profile reduced run --rm db-shell psql \
    -h postgres -U ${AGENT_API_DB_USER:-agent_api} -d ${AGENT_API_DB:-agent_reduced}
  ```

## 6. LocalStack vs Real AWS
- LocalStack is on by default (`USE_LOCALSTACK=1`). The services read `LOCALSTACK_HOST`, `LOCALSTACK_EDGE_PORT`, and `AWS_ENDPOINT_URL` from `.env`.
- To hit real AWS resources:
  1. Set `USE_LOCALSTACK=0`.
  2. Provide real `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (optionally) `AWS_SESSION_TOKEN`.
  3. Clear `AWS_ENDPOINT_URL` so SDKs resolve actual AWS endpoints.
  4. Restart any containers that talk to AWS (`docker compose restart agent-api`).
- LocalStack data lives in the `localstack_data` volume. Remove it with `docker volume rm housing-microservices_localstack_data` or `docker compose down -v` if you need a clean slate.

## 7. Production Mode with Compose
Use this workflow when you need the full stack with production-like settings, real secrets, and optional AWS access.

> AWS ingestion, curl walkthrough, and frontend endpoint reference live in [`docs/runbooks/prod_setup.md`](docs/runbooks/prod_setup.md). For a one-shot prod deploy (Terraform + EC2 compose), use `scripts/deploy_prod_stack.sh`. The ingestion endpoint is the FastAPI service on EC2 (`INGEST_BASE_URL=http://52.207.140.87:8085`).

1. **Prep environment files**
   ```bash
   cp env.example .env
   cp env.example .env.prod        # prod-only copy that stays gitignored
   ```
   Edit `.env` for dev/defaults and `.env.prod` for the prod profile, then `set -a && source .env.prod && set +a` before running prod compose. Use production-grade secrets:
   - Non-default JWT/signing secrets, database passwords, and API keys (`AGENT_OPENAI_API_KEY`, `EMAIL_PROVIDER_API_KEY`, etc.).
   - `STACK_PROFILE=full` and `COMPOSE_PROFILES=full,ops` so Compose launches every service plus helper containers.
   - `SERVICE_MODE=full` to turn on Valkey and pillar fallbacks.

2. **Decide on LocalStack vs AWS**
   - Keep `USE_LOCALSTACK=1` to emulate AWS. Ensure `AWS_ENDPOINT_URL=http://localstack:4566` (containers) or `http://localhost.localstack.cloud:4566` (host tooling), and reuse the default credentials baked into `env.example`.
   - Set `USE_LOCALSTACK=0` when you want the stack to talk to real AWS. Provide `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (optionally) `AWS_SESSION_TOKEN` plus the target region. Clear `AWS_ENDPOINT_URL` so SDKs auto-discover AWS endpoints and restart affected services (`docker compose restart agent-api`).
   - Prefer `scripts/use_env.sh aws` to copy your prod env into `.env.active` before running compose, `scripts/prod_smoke_check.sh`, or deployment helpers.

3. **Launch the full profile**
   ```bash
   STACK_PROFILE=full \
   COMPOSE_PROFILES=full,ops \
     docker compose --profile full up --build
   ```
   - The `ops` profile pulls in `db-shell` for manual SQL inspections.
   - Expect longer start times; keep `docker compose logs -f agent-api localstack` streaming in another terminal.

4. **Run smoke/validation hooks**
   - Execute `make reduced-e2e-smoke` from the repo root to run the reduced-profile automation against the same secrets before rolling out changes. Override `KEEP_STACK=1` if you want the reduced stack to stay up for debugging.
   - For full-stack-only checks, run `docker compose --profile full exec agent-api uv run python scripts/run_reduced_e2e_smoke.py run --report-path /app/logs/reduced_e2e_smoke.json` so the CLI interacts with live services without tearing them down.
   - See `docs/testing/reduced_e2e_smoke.md` for detailed CLI/Make usage and troubleshooting tips.

5. **Handoff reminders**
   - Regenerate `.env` secrets when onboarding new environments; never commit the edited file.
   - Document any production-only overrides inside `docs/runbooks/full_stack_compose.md` or the new reduced E2E smoke guide so future operators know which toggles you touched.

## 8. Troubleshooting Cheatsheet
| Symptom | Fix |
| --- | --- |
| Ports already in use | `lsof -i :8000`, stop conflicting process, then re-run Compose. |
| `db-init` fails with auth errors | Ensure `.env` passwords match `scripts/init-databases.sh` defaults or override them consistently. Rerun `docker compose run --rm db-init`. |
| LocalStack healthcheck flaps | Increase `LOCALSTACK_DEBUG=1` to inspect logs, or temporarily set `USE_LOCALSTACK=0` to bypass AWS emulation. |
| Services stuck in `starting` | Run `docker compose ps`, inspect `docker compose logs <service>`, verify `.env` copied from `env.example`. |
| Need a clean database | `docker compose down -v`, then start the stack again so `db-init` reseeds from scratch. |

## 9. Additional References
- `docs/runbooks/reduced_scope_demo.md` — detailed walkthrough of the reduced-profile workflow.
- `docs/runbooks/full_stack_compose.md` — full-stack LocalStack runbook (new in Task 05).
- `docs/infrastructure/root_compose_plan.md` — architectural decisions behind the root Compose stack.
- `docs/infrastructure/infrastructure_and_deployment.md` — AWS deployment strategy + how the local Compose mirrors it.

Questions? Start with the relevant runbook, then open an issue/PR with the context you gathered. Happy hacking! 🚀
