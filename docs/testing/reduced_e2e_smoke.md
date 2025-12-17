# Reduced E2E Smoke (Deprecated)

The reduced-scope smoke and demo toggles have been retired. Use the ingestion-first flow instead:
- Local: `./test-api.sh` after bringing up Compose with `.env.local`.
- Prod: `ENV_FILE=.env.prod ./scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_$(date +%s).log` (ingestion → activation → attach → chat).

All smokes must use the real ingestion service (MarkItDown → voyage-context-3 embeddings → pgvector) and the ReAct agent with `rerank-2.5`. Avoid cache/rate-limiter or Step Functions/Lambda references from earlier docs.
