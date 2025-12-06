# Task Tracker – FastAPI-Based Synchronous Ingestion Replacement
_Tracks TASK_PLAN_SYNC_FASTAPI_INGESTION.md (auto-approved)._

- [x] Step 1: Read new prompt and existing plan/tracker rows for numbering changes.
- [x] Step 2: Research FastAPI/MarkItDown sync ingestion references; log sources.
- [x] Step 3: Update task docs/plans to insert the new task and shift numbering; keep plan/tracker in sync.
- [x] Step 4: Design/implement FastAPI ingestion service (API parity, markitdown→chunk→embed→index→activate).
- [x] Step 5: Wire agent-api + smoke scripts to new service; update runbooks/endpoints.
- [x] Step 6: Add EC2 deploy automation for the new service (idempotent).
- [x] Step 7: Verify end-to-end ingestion on AWS; capture evidence and update tracker/docs.

Notes:
- New FastAPI service scaffold added under `services/ingestion-service` (MarkItDown conversion + chunk/embed pipeline) with Dockerfile and EC2 compose wiring; deploy script opens port 8085 and sets `INGEST_BASE_URL` to the new service.
- Smoke (AWS via FastAPI ingestion): `ENV_FILE=.env.active bash scripts/prod_smoke_check.sh | tee /tmp/prod_smoke_fastapi.log` succeeded; uploaded docs `2dc9b58f-217a-48a3-945c-8edae96c73c5`, `776f45dc-11e2-4b4a-b6b0-2c75bc39066c`, `bfbeb618-d493-47ef-a70a-f3d35d567277` ingested/attached and prompts completed.
