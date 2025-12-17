# Local Setup (LocalStack-first)

Run the retained stack locally (agent-api, ingestion-service, auth-service, user-service, Postgres, LocalStack). Valkey/cache, telemetry, and reduced-scope modes are deprecated.

## Prereqs
- Docker 25+ with Compose V2, bash, `curl`, `jq`.
- Env file: `.env.local` (seeded from `env.example` if missing).
- `OPENAI_API_KEY` and `VOYAGE_API_KEY` exported before starting agent-api.

## Steps
1) Load env  
   ```bash
   env_file=$(scripts/use_env.sh local)
   set -a && source "$env_file" && set +a
   ```
2) Start stack  
   ```bash
   docker compose --env-file "$env_file" up -d --build
   ./test-api.sh
   ```
3) Verify  
   ```bash
   curl -fsS http://localhost:${AUTH_SERVICE_PORT:-5001}/health
   curl -fsS http://localhost:${USER_SERVICE_PORT:-5002}/v1/health
   curl -fsS http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
   curl -fsS http://localhost:${AGENT_API_PORT:-8000}/health
   curl -fsS http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health
   ```
4) Stop/clean  
   ```bash
   docker compose --env-file "$env_file" down            # keep volumes
   docker compose --env-file "$env_file" down -v         # wipe data
   ```

## Notes
- Ingestion is synchronous and text-only (MarkItDown → Voyage `voyage-context-3` embeddings → pgvector activation).
- LocalStack is required for dev (`USE_LOCALSTACK=1` in `.env.local`) to mock AWS services; production bypasses it.
- Pyodide sandbox tool runs in Wasm with no filesystem; install extras with `micropip`/`httpx` inside the sandbox only.
