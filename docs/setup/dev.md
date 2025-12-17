# Dev Setup (Hybrid: local services, cloud data plane)

Run services locally while pointing at the shared AWS data plane (Postgres/S3/ingest). Use this for integration against the real stack without deploying containers to EC2.

## Prereqs
- Docker 25+ with Compose V2.
- Env file: `.env.dev` (contains AWS endpoints/creds, remote Postgres host).
- SSH key only needed for EC2 deploys, not for this mode.

## Steps
1) Load env
   ```bash
   env_file=$(scripts/use_env.sh dev)
   set -a && source "$env_file" && set +a
   ```
2) Run services against remote infra (no local Postgres)
   ```bash
   docker compose --env-file "$env_file" \
     -f docker-compose.ec2.yml \
     up -d --build agent-api auth-service user-service ingestion-service
   ```
3) Verify
   ```bash
   curl -fsS "$AUTH_BASE_URL/health"
   curl -fsS "$USER_BASE_URL/v1/health"
   curl -fsS "$AGENT_BASE_URL/health"
   curl -fsS "$INGEST_BASE_URL/health"
   ```
4) Stop
   ```bash
   docker compose --env-file "$env_file" -f docker-compose.ec2.yml down
   ```

## Notes
- `.env.dev` keeps CORS wide-open (`AGENT_API_CORS_ORIGINS=*`, `CORS_ORIGINS=*`) for team testing. Tighten as needed.
- `docker-compose.ec2.yml` skips the local Postgres container and binds ports to match the EC2/prod layout.
