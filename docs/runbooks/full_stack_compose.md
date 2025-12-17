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

## Local end-to-end smoke script
- Prereqs: compose stack up with `.env.local`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`.
- Run:  
  ```bash
  env_file=$(scripts/use_env.sh local)
  ENV_FILE="$env_file" ./scripts/local_smoke.sh
  ```
  (or `uv run bash scripts/local_smoke.sh`).
- Flow: registers a throwaway user, logs in, ingests docs from `services/agent-api/evals/data`, polls for activation, creates a conversation, bulk-attaches docs, asks grounded questions, and fails fast if answers are empty or lack citations.
- Output: JSON report at `local_smoke_report.json` with document IDs and Q/A details.

## Dev live-reload (faster local loops)
- Use the dev override to bind-mount code and enable reload:  
  ```bash
  env_file=$(scripts/use_env.sh local)
  docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file "$env_file" up -d
  ```
- Mounts: agent-api, ingestion-service, auth-service, and user-service source directories (plus shared_data_layer) are live-mounted into containers; uvicorn reloads on save.
- Rebuild images only when deps change (`pyproject.toml`/`uv.lock`); otherwise edits reload automatically.

## Stop/Clean
```bash
docker compose --env-file "$env_file" down              # keep volumes
docker compose --env-file "$env_file" down -v           # drop Postgres + LocalStack data
```

## Notes & constraints
- Ingestion is synchronous and text-only (MarkItDown → Voyage `voyage-context-3` embeddings → pgvector). Agent API never ingests directly.
- Graph RAG/planner, Valkey cache, telemetry collectors, and reduced-scope demos are deprecated; ignore older docs referencing them.
- Pyodide sandbox tool runs in Wasm with no filesystem; only `httpx`/`micropip` installs are allowed inside the sandbox.
