# Quick Start Guide

Spin up the Housing microservices stack (FastAPI gateway + legacy services) with the new root `docker compose` workflow. Follow these steps and you can interact with the demo in a few minutes.

## 1. Prerequisites
- Docker Desktop / Engine 25.x with Compose V2 (`docker compose`).
- Git + a bash-compatible shell.
- Optional: [uv](https://github.com/astral-sh/uv) if you need to run scripts or tests locally.

## 2. Clone & Copy Env
```bash
git clone <repo-url>
cd housing-microservices
cp env.example .env
```
Edit `.env` to set secure passwords, JWT secrets, and AWS credentials (if you plan to hit real AWS). Use `.env.local` for personal overrides.

## 3. Choose a Profile
| Profile | Command | Starts |
| --- | --- | --- |
| Reduced Agent API demo | `docker compose --profile reduced up --build agent-api` | Postgres + db-init + agent-api + db-shell + LocalStack for AWS mocks. |
| Full platform | `docker compose --profile full up --build` | All services (auth, user, swagger, agent, marker), LocalStack, Valkey, otel-collector. |
| Default (auth + user + swagger) | `docker compose up --build` | Legacy stack without agent-api (marker removed). |

Set `STACK_PROFILE=reduced` or `STACK_PROFILE=full` in your shell (or `.env`) so services know which runtime to activate. Override `COMPOSE_PROFILES` if you need extra helpers (e.g., `COMPOSE_PROFILES=full,ops`).

## 4. Launch & Verify
```bash
# Reduced profile example
STACK_PROFILE=reduced \
COMPOSE_PROFILES=reduced \
  docker compose --profile reduced up --build agent-api

# Full stack example
STACK_PROFILE=full \
COMPOSE_PROFILES=full \
  docker compose --profile full up --build
```
Once healthy, visit:
- Swagger UI: `http://localhost:${SWAGGER_SERVICE_PORT:-3000}`
- Agent API: `http://localhost:${AGENT_API_PORT:-8000}/docs`
- Auth health: `curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health`
- LocalStack status: `curl http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health`

## 5. Seed & Admin Tasks
- Seeding happens automatically via the `db-init` service. To rerun: `docker compose run --rm db-init`.
- Inspect the database: `docker compose --profile reduced run --rm db-shell psql -h postgres -U agent_api -d agent_reduced`.
- Run FastAPI CLI helpers: `docker compose --profile reduced exec agent-api uv run agent_api.cli --help`.
- Smoke test reduced profile: `services/agent-api/scripts/verify_reduced_scope_compose.sh`.

## 6. LocalStack vs AWS
- LocalStack is enabled by default (`USE_LOCALSTACK=1`).
- To use real AWS, set `USE_LOCALSTACK=0` and provide real AWS credentials in `.env`, then restart services that talk to AWS (`docker compose restart agent-api`).

## 7. Tear Down & Troubleshooting
```bash
docker compose down              # stop containers, keep volumes
docker compose down -v           # nuke Postgres + LocalStack data
```
Common fixes:
- **Ports busy**: `lsof -i :8000` and stop conflicting processes.
- **db-init failed**: confirm passwords in `.env` match `scripts/init-databases.sh`, then `docker compose run --rm db-init`.
- **LocalStack unhealthy**: check `docker compose logs localstack`, or temporarily set `USE_LOCALSTACK=0`.

For deeper instructions, read `docs/runbooks/reduced_scope_demo.md` (reduced profile) and `docs/runbooks/full_stack_compose.md` (full stack).
