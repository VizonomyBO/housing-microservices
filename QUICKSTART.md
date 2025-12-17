# Quick Start Guide

Spin up the simplified stack (agent-api, ingestion-service, auth-service, user-service, Postgres, LocalStack) with the root `docker compose` file.

## 1. Prerequisites
- Docker Desktop / Engine 25.x with Compose V2 (`docker compose`).
- Git + a bash-compatible shell.
- [uv](https://github.com/astral-sh/uv) if you need to run scripts or tests locally.

## 2. Pick an Environment
Use `scripts/use_env.sh` to pick the right env file and export it:
```bash
env_file=$(scripts/use_env.sh local|dev|prod)
set -a && source "$env_file" && set +a
```
`.env.local` is LocalStack-first; `.env.dev` points at the remote data plane; `.env.prod` targets AWS/EC2.

## 3. Bring Up the Dev Stack (LocalStack required)
```bash
docker compose --env-file "$env_file" up -d --build
./test-api.sh
```
Health probes:
```bash
curl http://localhost:${AUTH_SERVICE_PORT:-5001}/health
curl http://localhost:${USER_SERVICE_PORT:-5002}/v1/health
curl http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
```

## 4. Hybrid / Remote Data Plane (Optional)
Run the same services locally while pointing at remote databases/AWS:
```bash
env_file=$(scripts/use_env.sh dev)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service
```

## 5. Tear Down
```bash
docker compose --env-file "$env_file" down              # stop containers, keep volumes
docker compose --env-file "$env_file" down -v           # also delete Postgres + LocalStack data
```

## 6. Troubleshooting
- Agent API requires `OPENAI_API_KEY` and `VOYAGE_API_KEY`; set them before bringing the stack up.
- LocalStack must be healthy for dev: `curl http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health`.
- Rerun migrations if needed: `docker compose --env-file "$env_file" run --rm db-init`.
