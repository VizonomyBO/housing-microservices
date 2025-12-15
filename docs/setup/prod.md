# Prod Setup (AWS/EC2)

Use this flow to deploy to the shared AWS environment (EC2 services + remote Postgres + ingestion service). Full details remain in `docs/runbooks/prod_setup.md`; this page is the quick start.

## Prereqs
- Docker/Compose, Terraform 1.7+, AWS CLI, `jq`, `curl`, `uv` (optional).
- Env file: `.env.prod` (contains AWS creds, EC2 host, DB URLs, open CORS).
- SSH key: `ArchaaS/dist/vizonomy-v2-ec2-dev2.pem` (from Terraform outputs).

## Deploy + Smoke (quick path)
```bash
env_file=$(scripts/use_env.sh prod)
set -a && source "$env_file" && set +a

# Deploy infra + services (opens ports)
ENV_FILE="$env_file" ./scripts/deploy_prod_stack.sh --open-ports

# Verify health
curl -fsS "$AUTH_BASE_URL/health"
curl -fsS "$USER_SERVICE_URL/v1/health"
curl -fsS "$AGENT_BASE_URL/health"
curl -fsS "$INGEST_BASE_URL/health"

# AWS smoke via ingestion service (uploads PDFs, polls, attaches, chats)
ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```

## CORS posture
- `.env.prod` sets `AGENT_API_CORS_ORIGINS=*` and `CORS_ORIGINS=*` for testing. To allowlist, edit the env file, then redeploy (`deploy_ec2_services.sh --env-file .env.prod ...`).

## More detail
- See `docs/runbooks/prod_setup.md` for the full curl walkthrough, Terraform flags, and reset/cleanup steps.
