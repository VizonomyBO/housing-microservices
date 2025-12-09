# Housing Microservices Platform

FastAPI Agent API + auth/user services with a FastAPI-based ingestion service (EC2). Choose an env file for LocalStack (`.env.local`), hybrid dev (`.env.dev`), or AWS (`.env.prod`) and run/deploy with the commands below.

## Quick starts
- Pick env: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`
- Local (LocalStack): `COMPOSE_PROFILES=reduced,ops docker compose --env-file "$env_file" up -d --build`
- Dev (local services, cloud data plane): `docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`
- Prod deploy (AWS/EC2): `ENV_FILE="$env_file" ./scripts/deploy_prod_stack.sh --open-ports`
- Prod smoke: `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`

Setup guides: `docs/setup/local.md`, `docs/setup/dev.md`, `docs/setup/prod.md` (full prod runbook in `docs/runbooks/prod_setup.md`).

## Service inventory
| Service | Language | Host Port | Notes |
| --- | --- | --- | --- |
| agent-api | FastAPI + LangGraph | `${AGENT_API_PORT:-8000}` | Chat/SSE, documents, attachments. |
| ingestion-service | FastAPI | `${INGESTION_SERVICE_PORT:-8085}` | MarkItDown → chunk → embed → index; replaces Lambda/S3 path. |
| auth-service | Flask | `${AUTH_SERVICE_PORT:-5001}` | Issues JWTs. |
| user-service | Flask | `${USER_SERVICE_PORT:-5002}` | User management. |
| swagger-service | Node/Express | `${SWAGGER_SERVICE_PORT:-3000}` | Optional aggregated docs. |
| postgres | pgvector 16 | `${POSTGRES_PORT:-5432}` | Shared DB (housing/auth_db). |
| localstack/valkey/otel | optional | various | Only in local profiles. |

## Local reduced scope
```bash
env_file=$(scripts/use_env.sh local)
set -a && source "$env_file" && set +a
COMPOSE_PROFILES=reduced,ops docker compose --env-file "$env_file" up -d --build
curl http://localhost:${AGENT_API_PORT:-8000}/health
curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health
```
Stop: `docker compose --env-file "$env_file" down [-v]`

## Dev hybrid (local services, cloud data plane)
```bash
env_file=$(scripts/use_env.sh dev)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service
```
Health checks use the URLs from `.env.dev` (e.g., `http://52.207.140.87:8000/health`).

## Prod deploy summary
See `docs/setup/prod.md` for the quick path and `docs/runbooks/prod_setup.md` for full curls/terraform.
```bash
env_file=$(scripts/use_env.sh prod)
set -a && source "$env_file" && set +a
ENV_FILE="$env_file" ./scripts/deploy_prod_stack.sh --open-ports
ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```

## Quality gates (agent-api)
```bash
cd services/agent-api
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```
