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
2) Start the reduced stack (postgres + services + LocalStack)
   ```bash
   COMPOSE_PROFILES=reduced,ops \
     docker compose --env-file "$env_file" up -d --build
   ```
3) Verify
   ```bash
   curl -fsS http://localhost:${AGENT_API_PORT:-8000}/health
   curl -fsS http://localhost:${AUTH_SERVICE_PORT:-5001}/health
   curl -fsS http://localhost:${LOCALSTACK_EDGE_PORT:-4566}/_localstack/health
   ```
4) Stop/clean
   ```bash
   docker compose --env-file "$env_file" down            # keep volumes
   docker compose --env-file "$env_file" down -v         # wipe data
   ```

## Notes
- LocalStack mode is deferred in current workstreams, but this layout keeps parity with AWS env vars (`USE_LOCALSTACK=1` in `.env.local`).
- If you change ports or add services, update `.env.local` so compose picks them up.
