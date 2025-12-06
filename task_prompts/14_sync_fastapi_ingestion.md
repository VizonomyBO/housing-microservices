# Task 14 – Replace Lambda ingestion with a simple FastAPI service on EC2

## Objective
**Status: Completed.** The Lambda-based ingestion flow has been replaced with a single FastAPI app on EC2 (port 8085) that performs synchronous PDF ingestion end-to-end using MarkItDown, chunking, embeddings, and activation. No Redis/workers—just a long-running process handling the full pipeline. The API surface mirrors the prior ingestion Lambda interface so upstream clients (agent-api, scripts, smoke) continue to work.

## Requirements (fulfilled)
- FastAPI service (`services/ingestion-service`, port 8085) with uv-managed venv; upload endpoint returns signed form fields and sync-ingests (MarkItDown → chunk → embed → activate).
- Payload compatibility with prior ingestion (document_id, ingestion_id, tags, trace_id, callback_url, etc.) so agent-api and smoke scripts work unchanged.
- Lambda/S3 path bypassed; `INGEST_BASE_URL` now points to the FastAPI service; scripts/runbooks updated accordingly.
- Deployed on the existing EC2 host alongside other services via `docker-compose.ec2.yml` and `scripts/deploy_ec2_services.sh` (opens 8085).
- Parity: docs convert/chunk/embed, reach `active`, and attach; attachment safety still enforced in agent-api.

## Deliverables (completed)
- FastAPI ingestion service code + uv venv setup; deploy manifest/compose entry for EC2.
- Wiring updated so agent-api and smoke/tests hit this service instead of Lambda/S3.
- Documentation/runbook updated to reflect the new ingestion path and EC2 deployment.
- Old Lambda ingestion path bypassed for prod flows.
