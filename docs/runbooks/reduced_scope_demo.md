# Reduced Scope Demo (Deprecated)

The reduced-scope/Valkey-backed demo and Step Functions/Lambda simulators are no longer part of the supported stack. Use the standard ingestion-first flow instead:
- Local dev: `docker compose --env-file "$(scripts/use_env.sh local)" up -d --build` then `./test-api.sh`.
- Hybrid dev: `docker compose --env-file "$(scripts/use_env.sh dev)" -f docker-compose.ec2.yml up -d --build agent-api auth-service user-service ingestion-service`.
- Prod smoke: `ENV_FILE=.env.prod ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log`.

Graph RAG, cache/rate-limiter wiring, and reduced-scope toggles remain in the repo only for archival context; do not use them for new work.
