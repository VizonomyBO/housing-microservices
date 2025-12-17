# Dev Setup (Hybrid: local services, remote data plane)

Run the services locally while pointing at the shared AWS data plane (Postgres/S3/ingestion). Use this for integration against the real stack without deploying new containers to EC2.

## Prereqs
- Docker 25+ with Compose V2.
- Env file: `.env.dev` (AWS endpoints/creds, remote Postgres host).

## Steps
1) Load env  
   ```bash
   env_file=$(scripts/use_env.sh dev)
   set -a && source "$env_file" && set +a
   ```
2) Start services against remote infra (no local Postgres)  
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
- `.env.dev` keeps CORS permissive for team testing; tighten before exposing beyond dev.
- `docker-compose.ec2.yml` omits the local Postgres container and uses remote endpoints from the env file.
- Ingestion remains synchronous/text-only; graph/cache/reduced-scope modes are deprecated.
