# Reduced Scope Demo Runbook

This runbook walks through the Epic 3.5 “text-only, no-Valkey” experience using the root `docker-compose.yml`. The reduced profile launches just enough infrastructure for FastAPI + Postgres while keeping the production architecture (LangGraph nodes, seed scripts, LocalStack) behind feature flags. For the automation/CLI view, pair this document with `docs/testing/reduced_e2e_smoke.md`.

## 1. Prerequisites
- Docker 25.x with Compose V2 (`docker compose`).
- Git + bash-compatible shell.
- Optional: [uv](https://github.com/astral-sh/uv) if you need to run CLI helpers or smoke tests locally.

## 2. Environment Prep
1. From the repo root:
   ```bash
   cp env.example .env
   ```
2. Set/confirm the following variables in `.env` or your shell:
   - `STACK_PROFILE=reduced`
   - `COMPOSE_PROFILES=reduced` (adds the reduced profile in addition to Compose’s `default` services).
   - `SERVICE_MODE=reduced` and `REDUCED_SCOPE_*` flags should remain `1`.
   - `USE_LOCALSTACK=1` for mocked AWS endpoints (default). Set to `0` only if you have real AWS credentials.
   - `AUTH_SHARED_SECRET`/`AUTH_JWKS_URL` to control JWT validation. Leave `AUTH_JWKS_URL` empty until auth-service publishes JWKS metadata; ensure `AUTH_SHARED_SECRET` matches `JWT_SECRET_KEY` so HS256 dev tokens stay valid.
   - For “real tooling” runs: set `REDUCED_SCOPE_USE_REAL_TOOLS=1` (or export `REAL_REDUCED_E2E_TOOLS=1` when using the smoke wrapper) **and** provide `OPENAI_API_KEY` + `VOYAGE_API_KEY`. The Agent API now fails fast if those secrets are missing when real mode is requested.
3. Optional: create `.env.local` (gitignored) for developer-specific overrides and `source` it before running Compose.

## 3. Launch Sequence
```bash
STACK_PROFILE=reduced \
COMPOSE_PROFILES=reduced \
  docker compose --profile reduced up --build agent-api
```
- `scripts/run_reduced_e2e_compose.sh` mirrors this behavior: when `USE_LOCALSTACK=0` it omits the LocalStack container entirely and runs the smoke CLI without the `--localstack-url` probe so every AWS call hits the real endpoint you configured.
- `postgres` starts immediately because it has no profile restrictions.
- `db-init` waits for Postgres to become healthy, then runs Alembic migrations and `services/agent-api/scripts/seed_reduced_scope_data.py --if-empty`.
- `agent-api` starts once `db-init` completes successfully. When `USE_LOCALSTACK=1`, LocalStack joins the stack so S3/EventBridge clients resolve to mock endpoints; set `USE_LOCALSTACK=0` to skip the container and rely on real AWS services instead.

### Smoke Verification (Optional but Recommended)
Run the helper script from the Agent API service directory:
```bash
cd services/agent-api
./scripts/verify_reduced_scope_compose.sh
```
This wraps `docker compose --profile reduced config` for linting and executes `pytest -k reduced_scope_smoke` to ensure demo endpoints stay healthy.

> Heads-up: the reduced smoke CLI now provisions conversations/resets demo data exclusively via HTTP (`/v1/conversations`, `/v1/demo/*`). You no longer need to expose `DATABASE_URL` to the CLI; instead toggle cleanup stages with `REDUCED_E2E_RESEED_DOCS=1` or `REDUCED_E2E_CLEANUP_ONLY=1` when invoking the wrapper/Make target.

### Real Tooling Mode Checklist
- **When to use**: set `REDUCED_SCOPE_USE_REAL_TOOLS=1` anytime you need to validate OpenAI chat completions + Voyage embeddings inside the reduced stack (CI smoke, operator demos, etc.).
- **Secrets**: `OPENAI_API_KEY` and `VOYAGE_API_KEY` must be present in `.env`/`.env.local`. The FastAPI app exits during startup if either secret is missing while the flag is enabled.
- **Wrapper shortcut**: export `REAL_REDUCED_E2E_TOOLS=1 make reduced-e2e-smoke` (or pass the env var directly to `scripts/run_reduced_e2e_compose.sh`). The wrapper now propagates the flag into Docker, sets the Typer CLI’s `--use-real-tools` option, and mirrors the state via `REAL_REDUCED_E2E_TOOLS` inside the container.
- **Limited exceptions**: even in real mode, only Valkey/cache wiring and image/table ingestion remain stubbed. Any other shortcut (fake rate limits, text-only ingestion, etc.) must be treated as a regression.

### Authentication Tokens

- The smoke CLI now registers (or reuses) the demo account and calls `/v1/auth/login` on auth-service to obtain a real JWT before it touches the Agent API. If the login stage fails, inspect `auth-service` logs—the API will now reject every request without a valid token.
- Manual API explorations must propagate that JWT via the `Authorization: Bearer <token>` header. To fetch one quickly:
  ```bash
  curl -s http://localhost:${AUTH_SERVICE_PORT:-5001}/v1/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"login":"ava.reduced+demo@example.com","password":"DemoPassw0rd!"}' \
    | jq -r '.access_token'
  ```
- Update the login payload if you override the demo credentials via `REDUCED_E2E_*` env vars. Tokens expire after 15 minutes by default; rerun the command (or the smoke CLI) whenever the Agent API returns `401`.

## 4. Interacting With the Stack
| Action | Command / URL |
| --- | --- |
| FastAPI docs | `http://localhost:${AGENT_API_PORT:-8000}/docs` |
| Chat stream smoke | `curl http://localhost:${AGENT_API_PORT:-8000}/health` |
| Browse seeded documents | `GET /v1/documents?limit=5` via the FastAPI docs |
| CLI helpers | `docker compose --profile reduced exec agent-api uv run agent_api.cli --help` |
| PostgreSQL shell | `docker compose --profile reduced run --rm db-shell psql -h postgres -U agent_api -d agent_reduced` |
| LocalStack health | `curl http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health` |

## 5. Seeding & Maintenance
- Rerun seed logic at any time:
  ```bash
  docker compose run --rm db-init
  ```
- Force-reseed with CLI:
  ```bash
  docker compose --profile reduced exec agent-api \
    uv run python scripts/seed_reduced_scope_data.py --force
  ```
- Tail logs when debugging: `docker compose logs -f agent-api`, `docker compose logs -f db-init`.

## 6. Teardown & Reset
```bash
docker compose --profile reduced down       # stop reduced profile containers
docker compose --profile reduced down -v    # also delete Postgres + LocalStack volumes
```
Use the `-v` flag whenever you want to rebuild the demo database from scratch. Restarting afterward automatically runs `db-init` with fresh seeds.

## 7. Switching Back to Full Mode
1. Update `.env` or your shell:
   ```bash
   export STACK_PROFILE=full
   export COMPOSE_PROFILES=full
   export USE_LOCALSTACK=0   # optional if you have real AWS credentials
   ```
2. Run `docker compose --profile full up --build` to start every service.
3. Refer to `docs/runbooks/full_stack_compose.md` for the full workflow (LocalStack toggle, marker-service flows, telemetry).

## 8. Troubleshooting
| Symptom | Action |
| --- | --- |
| `db-init` exits non-zero | Ensure `.env` passwords match `scripts/init-databases.sh` defaults, then `docker compose run --rm db-init`. |
| Agent API stuck in `starting` | Check `docker compose logs agent-api` for missing env vars; confirm `STACK_PROFILE=reduced`. |
| LocalStack healthcheck fails | Inspect `docker compose logs localstack`; set `LOCALSTACK_DEBUG=1` for verbose output. |
| API calls return 401 | Fetch a fresh JWT from auth-service (see Authentication Tokens above) and include it via `Authorization: Bearer <token>`. |
| Need to bypass LocalStack | Set `USE_LOCALSTACK=0`, provide real AWS creds, and `docker compose restart agent-api`. |

Keep this runbook close whenever you demo LangGraph features without the rest of the platform. For the complementary full-stack experience, see `docs/runbooks/full_stack_compose.md`.
