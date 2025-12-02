# Task 02 — Text-only Document, Attachment & Pillar APIs

## System Snapshot
- Task 01 introduced ReducedScope flags, disabled Valkey/rate limiting, and forced `/v1/chat` + LangGraph nodes into text-only mode.
- `packages/shared_data_layer` already exposes document, chunk, ingestion job, and pillar-related repositories; `/v1/chat` relies on those tables for retrieval scope.
- FastAPI currently only serves `/v1/chat` and `/metrics`; document upload/attachment/pillar endpoints do not exist yet in `services/agent-api`.

## What You Inherit
- ReducedScope settings + demo-mode SSE headers from Task 01.
- Full document + attachment repositories (`services/agent-api/src/repositories/*`, `packages/shared_data_layer/repositories/documents.py`) and Text-to-SQL helpers (`subgraphs/numerical/text_to_sql_node.py`).
- Docs describing the prior (full) API contract (`docs/interfaces/api_contracts.md`) and schema expectations (`docs/data/schema_and_persistence.md`).

## Goal
Expose text-only upload, attachment, and pillar endpoints that behave synchronously: reject image/table ingestion with 202 “feature disabled” responses, auto-complete ingestion jobs for markitdown text, and return JSON pillar aggregates instead of PDF exports—all while updating docs/tests so clients know what to expect during the demo build.

## Must Read Before Coding
1. `docs/epics/035.md` — Task 3.5.2 scope.
2. `docs/data/schema_and_persistence.md` §§3.1–3.4 — documents, chunks, ingestion jobs, pillar tables.
3. `docs/interfaces/api_contracts.md` §§2–4 — document upload, attachment, and pillar contracts.
4. `docs/overview/system_architecture.md` §3 — how attachments feed LangGraph/text-to-sql.
5. `docs/agents/implementation.md` §§4.1–4.3 — Informational/Analyst/Numerical subgraphs + attachment scope loaders.

## Implementation Scope & Files
- Create new FastAPI routers: `agent_api/http/routes/documents.py`, `agent_api/http/routes/attachments.py`, and `agent_api/http/routes/pillars.py`, plus accompanying request/response schemas in `agent_api/http/schemas.py` (or new modules) for uploads, attachment operations, and pillar JSON payloads.
- Update `agent_api/http/app.py` to include the new routers and ensure they respect ReducedScope headers + SSE metadata.
- Implement services/helpers:
  - `services/agent-api/src/services/ingestion_job_service.py` — synchronous helpers to create + auto-complete `ingestion_jobs` rows when only text chunks are accepted.
  - `services/agent-api/src/services/document_upload_service.py` and `services/agent-api/src/services/attachment_service.py` — wrap shared-data-layer repositories, enforce `chunk_type == 'text'`, and emit TODO markers showing where non-text flows reattach later.
  - `services/agent-api/src/services/pillar_service.py` — reuse Text-to-SQL utilities to assemble JSON responses for `GET /v1/pillars/{country_code}` and `/v1/conversations/{id}/pillars` (citations + metadata only; PDF exports deferred with TODOs).
- Guard ingestion + attachment logic with ReducedScope flags: respond with HTTP 202 + `{ "status": "feature_disabled", "message": "image ingestion paused" }` when payload includes `chunk_type in ('image','table')`, and store `{"status":"skipped"}` metadata rows instead of deleting structure.
- Update shared fixtures or repositories only as needed (e.g., add helper to `packages/shared_data_layer/repositories/documents.py` if ingestion job completion needs a dedicated method) and document the change in that package’s AGENT guide if touched.
- Documentation updates: add a “Reduced Scope” callout in `docs/interfaces/api_contracts.md` for each endpoint, plus `docs/agents/implementation.md` & `docs/data/schema_and_persistence.md` notes on the synchronous ingestion helper + metadata stubs.
- Tests: new coverage under `services/agent-api/tests/http/test_documents_route.py`, `.../test_attachments_route.py`, `.../test_pillars_route.py`, plus service-layer unit tests for ingestion job helpers and pillar aggregation (reusing shared_data_layer factories/Testcontainers).

## Step-by-Step Instructions
1. **Build synchronous ingestion helpers**:
   - Implement `ReducedScopeIngestionJobService` that can (a) insert a minimal `ingestion_jobs` row, (b) mark it `succeeded` immediately with stored timestamps, and (c) attach metadata stubs `{"reduced_scope": true}`. Add unit tests using shared_data_layer factories to verify DB writes and chunk filters.
2. **Add document & attachment routes**:
   - Define request schemas that only accept `content_type="text/markdown"` + markitdown payloads. Reject image/table chunks with 202 + `Retry-After` header referencing the future feature. Auto-attach base documents per `docs/data/schema_and_persistence.md` §3 when `auto_attach_base_docs` or ReducedScope hints require it, but wrap any table/image metadata enrichment in `if not settings.reduced_scope.text_only` guards.
3. **Expose pillar JSON endpoints**:
   - Implement synchronous `GET /v1/pillars/{country_code}` + optional `/v1/conversations/{id}/pillars` that run Text-to-SQL aggregations over text chunks only, returning JSON with citations + metadata for the frontend. Add TODO comments where deferred PDF/export logic will plug back in and update API docs/test fixtures accordingly.

## Definition of Done
- New document, attachment, and pillar HTTP routes exist, mounted in FastAPI, and all reject/short-circuit non-text payloads with clear demo-mode messaging.
- Ingestion job helpers auto-complete markitdown uploads and record skipped metadata for hidden attachment enrichments.
- Pillar endpoints return synchronous JSON responses derived from text-only chunks and cite the shared-data-layer queries they use.
- Tests cover upload/attachment happy paths, rejection paths, and pillar aggregation; run `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, and `uv run pytest -n auto`.
- Docs updated so clients understand the reduced-scope behavior.
- **Handoff Notes**: Execution agent must state which helper modules/endpoints were added, how ingestion job shortcuts are recorded, and which TODO markers point to re-enabling async exports.

## Handoff Notes
- Provide API examples (request/response bodies) and fixture names for the synchronous endpoints for Task 03.
- Call out any shared_data_layer changes or migrations so the next agent can reuse them when wiring the workerless runtime.
- Document how pillar JSON payloads encode citations/metadata so frontend + Task 03 remain aligned.
- Task 01 wired `ReducedScopeSettings` + `demo_mode_skipped` SSE events; reuse `settings.reduced_scope.allowed_chunk_types` + `ReducedScopeRateLimiter` when gating uploads/attachments.
