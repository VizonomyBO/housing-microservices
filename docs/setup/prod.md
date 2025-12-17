# Prod Setup (AWS/EC2)

Quick start for the ingestion-first stack on EC2. Full walkthrough lives in `docs/runbooks/prod_setup.md`.

## Prereqs
- Docker/Compose, Terraform 1.7+, AWS CLI, `jq`, `curl`.
- Env file: `.env.prod` (AWS creds, EC2 host, DB URLs, CORS).
- SSH key from Terraform outputs (e.g., `ArchaaS/dist/vizonomy-v2-ec2-dev2.pem`).

## Deploy + smoke
```bash
env_file=$(scripts/use_env.sh prod)
set -a && source "$env_file" && set +a

# Deploy infra + services (preserves DB unless --destroy-first)
ENV_FILE="$env_file" ./scripts/deploy_stack.sh --mode full-redeploy

# Health
curl -fsS "$AUTH_BASE_URL/health"
curl -fsS "$USER_BASE_URL/v1/health"
curl -fsS "$AGENT_BASE_URL/health"
curl -fsS "$INGEST_BASE_URL/health"

# Smoke: ingestion → activation → attach → chat
ENV_FILE="$env_file" ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log
```

## Notes
- Stack is text-only: ingestion-service runs MarkItDown → contextual chunking → Voyage `voyage-context-3` embeddings → pgvector activation; Agent API never ingests directly.
- Graph/Step Functions/Valkey/reduced-scope/telemetry features are deprecated.
- `.env.prod` ships permissive CORS (`AGENT_API_CORS_ORIGINS=*`, `CORS_ORIGINS=*`) for testing; tighten and redeploy as needed.
