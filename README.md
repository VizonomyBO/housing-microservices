# Housing Microservices Platform

FastAPI Agent API + auth/user services with a FastAPI-based ingestion service. Pick an env file for LocalStack dev (`.env.local`), hybrid/remote data plane (`.env.dev`), or AWS (`.env.prod`) and run with the commands below.

## Quick starts
- Pick env: `env_file=$(scripts/use_env.sh local|dev|prod); set -a && source "$env_file" && set +a`
- Dev stack (LocalStack required): `docker compose --env-file "$env_file" up -d --build`
- Hybrid/EC2 compose (optional): `docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`
- Prod deploy (AWS/EC2): `ENV_FILE="$env_file" ./scripts/deploy_prod_stack.sh --open-ports`
- Prod smoke: `ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`

Stop: `docker compose --env-file "$env_file" down [-v]`

## Service inventory
| Service | Language | Host Port | Notes |
| --- | --- | --- | --- |
| agent-api | FastAPI + LangGraph | `${AGENT_API_PORT:-8000}` | Chat/SSE, attachments; upload via ingestion service (Agent API no longer ingests). |
| ingestion-service | FastAPI | `${INGESTION_SERVICE_PORT:-8085}` | MarkItDown → chunk → embed → index; required upload path (no inline ingestion). |
| auth-service | Flask | `${AUTH_SERVICE_PORT:-5001}` | Issues JWTs. |
| user-service | Flask | `${USER_SERVICE_PORT:-5002}` | User management. |
| postgres | pgvector 16 | `${POSTGRES_PORT:-5432}` | Shared DB (housing/auth_db). |
| localstack | LocalStack | `${LOCALSTACK_EDGE_PORT:-4566}` | Required for dev S3/AWS mocks. |

## Local dev (Postgres + LocalStack)
```bash
env_file=$(scripts/use_env.sh local)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" up -d --build
./test-api.sh
curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health
curl http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
```
Stop: `docker compose --env-file "$env_file" down [-v]`

## Hybrid/remote data plane (optional)
```bash
env_file=$(scripts/use_env.sh dev)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service
```
Point `AUTH_BASE_URL`/`INGEST_BASE_URL`/`AGENT_BASE_URL` to the remote endpoints you want to smoke.

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
