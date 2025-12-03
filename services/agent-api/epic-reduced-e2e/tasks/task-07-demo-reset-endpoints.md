# Task 07 — Demo Reset & Data Hygiene Endpoints

## System Snapshot
- After Task 06, clients can create conversations via HTTP, but there is no supported way to clean up demo data (documents, attachments, conversations) without DB access.
- Re-running the reduced smoke workflow multiple times can trigger dedupe errors (document already uploaded) or leave orphaned attachments, complicating repeatable testing.
- Operators currently resort to `docker compose down -v` or manual SQL to reset state, which is slow and not CI-friendly.

## What You Inherit
- Conversation/doc upload/chat endpoints plus the new `/v1/conversations` route.
- Shared data layer repositories capable of deleting attachments and conversations with cascading rules.
- Local-only authentication context (reduced profile) where exposing admin-style operations is acceptable when gated by role or special header.

## Goal
Provide HTTP endpoints that allow CI and local operators to reset demo data safely without direct database access. At minimum:
1. `POST /v1/demo/reset-conversation` — Detaches documents, deletes attachments/chat history for a given conversation owned by the caller (defaulting to the deterministic reduced-e2e conversation if not specified).
2. `POST /v1/demo/purge-documents` — Deletes uploaded documents tied to the caller (optionally limited to fixture hashes) so the next smoke run can re-upload without conflict.
3. Optional: `POST /v1/demo/reseed` — Triggers a lightweight reseed routine (e.g., calls existing seed script) when running inside the container; ensure it’s idempotent and gated.

## Must Read / Inspect
1. `tests/scripts/test_reduced_e2e_fixtures.py` and fixture manifest for how documents are hashed/dedupe’d.
2. `agent_api/http/routes/documents.py` to understand current upload dedupe errors.
3. `scripts/run_reduced_e2e_smoke.py` for where reset hooks will be invoked.
4. Shared data layer deletion semantics (repositories + Alembic constraints) so cascading deletes are safe.

## Implementation Scope & Deliverables
- Add a new router (e.g., `src/agent_api/http/routes/demo.py`) grouped under `/v1/demo/*` with `tags=["demo"]` and explicit `ReducedScopeFlags` guard so it’s only active when `SERVICE_MODE=reduced`.
- Implement the endpoints above with request schemas that allow specifying `conversation_id`, `document_aliases`, or `content_hashes`. Each should validate ownership and return structured results (`{"purged_documents": N}` etc.).
- Wire in telemetry/logging so accidental production exposure is detectable (e.g., warn if `SERVICE_MODE` not reduced).
- Extend the smoke CLI to optionally call `POST /v1/demo/reset-conversation` when `--reseed-docs` or `--cleanup` flags are passed (no more direct DB deletes).
- Write API tests covering success, unauthorized access, attempts to purge conversations owned by another user, and error edge cases (unknown conversation/document).
- Update `docs/testing/reduced_e2e_smoke_plan.md` + `docs/testing/reduced_e2e_smoke.md` to explain the new reset workflow.

## Step-by-Step
1. Design request/response schemas and update OpenAPI docs/comments for clarity.
2. Implement the router with dependency injection for auth context, DB session, and reduced scope flags.
3. Add service/repository helpers for deleting attachments/documents safely (consider wrapping in transactions).
4. Update CLI flags (`--reseed-docs`, `--cleanup-only`) to invoke the new endpoints before uploading fixtures.
5. Write unit/integration tests (FastAPI TestClient) for each endpoint plus CLI tests mocking the new HTTP calls.
6. Refresh documentation + checklist, run the mandatory QA suite.

## Definition of Done
- `/v1/demo/reset-conversation` and `/v1/demo/purge-documents` exist, gated to reduced scope and authenticated users.
- Smoke CLI can reset state via HTTP without touching the database directly.
- Docs describe the reset process, and tests verify ownership + error handling.

## Handoff Notes
- If future tasks need broader admin powers (e.g., cross-user purge), note the required safeguards (role checks, feature flags) here.
- Document any assumptions about fixture hashes so Task 09+ can keep them in sync.
