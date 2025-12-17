# Reduced E2E Smoke Plan (Deprecated)

Legacy reduced-scope/demo coverage has been replaced by the ingestion-first smokes:
- Local API smoke: `./test-api.sh` after starting Compose with `.env.local`.
- Prod smoke: `ENV_FILE=.env.prod ./scripts/prod_smoke_check.sh` (uploads stamped PDFs via ingestion-service → waits for `status=active` → attaches → chats).

Do not add new reduced-mode scenarios. Graph RAG, Step Functions/Lambda ingestion, Valkey cache/rate limiter, and telemetry extras are archived and should not be used in tests.
