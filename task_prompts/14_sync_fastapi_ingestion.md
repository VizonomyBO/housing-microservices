# Task 14 – Replace Lambda ingestion with a simple FastAPI service on EC2

## Objective
Retire the Lambda-based ingestion flow and replace it with a single FastAPI app (running on EC2 alongside the other services) that performs synchronous PDF ingestion end-to-end using MarkItDown, chunking, embeddings, and activation. No Redis/workers—just a long-running process handling the full pipeline. The API surface must mirror the current ingestion Lambda interface so upstream clients (agent-api, scripts, smoke) continue to work.

## Requirements
- Build a FastAPI service with its own uv-managed venv; expose an upload endpoint matching the existing ingestion API contract (presign + fields compatibility or a direct upload that preserves the same request/response shape).
- Perform ingestion synchronously: download/process the PDF, convert with MarkItDown, chunk, embed, index, and mark the document ready, all within the request/response lifecycle (or a single long-running process without background workers).
- Maintain payload compatibility with the Lambda workflow (same fields: document_id, content_hash, tags, trace_id, callback_url, etc.) so agent-api and smoke scripts continue to function without client changes.
- Remove or bypass the Lambda/S3-trigger path as needed (“nuke all needed”); wire agent-api and any helpers to call this FastAPI service instead of API Gateway/S3/Lambda for ingestion.
- Deploy the FastAPI ingestion service on the existing EC2 host with the other services; keep it as simple as possible (no Redis, no workers, no additional infra).
- Keep functionality parity with the previous pipeline: documents convert, chunk, embed/index, and become attachable/active; attachment safety remains enforced.

## Deliverables
- FastAPI ingestion service code + uv venv setup; deploy manifest/compose entry for EC2.
- Updated wiring so agent-api and smoke/tests hit this service instead of the Lambda/S3 flow.
- Documentation/runbook updates reflecting the new ingestion path and how to run it on EC2.
- Removal/disablement of the old Lambda ingestion flow if necessary to prevent conflicts.
