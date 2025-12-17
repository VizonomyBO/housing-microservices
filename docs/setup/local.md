# Local Setup (LocalStack-first)

Use this when running everything on your machine with LocalStack emulating AWS.

## Prereqs
- Docker 25+ with Compose V2, Python 3.11+, `uv` installed.
- Env file: `.env.local` (seeded from `env.example` if missing).

## Steps
1) Load env
   ```bash
   env_file=$(scripts/use_env.sh local)
   set -a && source "$env_file" && set +a
   ```
2) Start the stack (Postgres + services + LocalStack)
   ```bash
   docker compose --env-file "$env_file" up -d --build
   ./test-api.sh
   ```
3) Verify
   ```bash
   curl -fsS http://localhost:${AUTH_SERVICE_PORT:-5001}/health
   curl -fsS http://localhost:${USER_SERVICE_PORT:-5002}/v1/health
   curl -fsS http://localhost:${INGESTION_SERVICE_PORT:-8085}/health
   curl -fsS http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health
   ```
4) Stop/clean
   ```bash
   docker compose --env-file "$env_file" down            # keep volumes
   docker compose --env-file "$env_file" down -v         # wipe data
   ```

## Notes
- LocalStack is required for dev (`USE_LOCALSTACK=1` in `.env.local`) to mock S3/AWS services.
- If you change ports or add services, update `.env.local` so compose picks them up.
