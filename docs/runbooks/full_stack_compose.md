# Compose Runbook (Retained Services)

Use this runbook to run the active stack locally: agent-api, ingestion-service, auth-service, user-service, Postgres, and LocalStack. Valkey/cache, telemetry, Step Functions, and reduced-scope profiles are deprecated and removed.

## Prerequisites
- Docker 25.x with Compose V2, bash, `curl`, `jq`.
- Env file via `scripts/use_env.sh local|dev|prod`; LocalStack is required for dev.
- `OPENAI_API_KEY` and `VOYAGE_API_KEY` exported before starting agent-api.

## Start
```bash
env_file=$(scripts/use_env.sh local)
set -a && source "$env_file" && set +a
docker compose --env-file "$env_file" up -d --build
```
- Services: postgres, db-init (shared_data_layer migrations), localstack, auth-service, user-service, ingestion-service, agent-api.

## Verify
```bash
./test-api.sh
curl -fsS http://localhost:${AUTH_SERVICE_PORT:-5001}/health
curl -fsS http://localhost:${USER_SERVICE_PORT:-5002}/v1/health
curl -fsS http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
curl -fsS http://localhost:${AGENT_API_PORT:-8000}/health
curl -fsS http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health
```

## Smoke (manual)
See `QUICKSTART.md` for the inline upload/attach/chat snippet or run the prod-mode helper against AWS:  
`ENV_FILE=.env.prod ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`

## Stop/Clean
```bash
docker compose --env-file "$env_file" down              # keep volumes
docker compose --env-file "$env_file" down -v           # drop Postgres + LocalStack data
```

## Notes & constraints
- Ingestion is synchronous and text-only (MarkItDown → Voyage `voyage-context-3` embeddings → pgvector). Agent API never ingests directly.
- Graph RAG/planner, Valkey cache, telemetry collectors, and reduced-scope demos are deprecated; ignore older docs referencing them.
- Pyodide sandbox tool runs in Wasm with no filesystem; only `httpx`/`micropip` installs are allowed inside the sandbox.
