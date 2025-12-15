# Task 08 — Conversation & Document Utility Endpoints

## System Snapshot
- Users now can create conversations (Task 06) and reset data (Task 07), but there is no way for a frontend to list existing conversations or uploaded documents via the agent API.
- The smoke CLI currently tracks uploaded document IDs in-memory; a real UI would query the API to render selectable conversations/docs.
- Without list/search endpoints, operators must inspect the database or rely on internal tooling.

## What You Inherit
- Conversation/doc models + new lifecycle/reset endpoints.
- Shared data layer repositories that already include query helpers.
- OpenAPI/fastapi infrastructure and pagination helpers used by other services (e.g., `pillars`, `metrics`).

## Goal
Expose read-only utility endpoints so authenticated users can enumerate their conversations and documents. Requirements:
1. `GET /v1/conversations` — Returns the caller’s conversations with pagination (`page`, `page_size`), filtering (tags, country), and summary metadata (last updated timestamp, attached document count).
2. `GET /v1/documents` — Lists uploaded documents accessible to the caller (filter by tag, content hash, created window) and surfaces ingestion status + content hash for verification.
3. Optional `GET /v1/conversations/{conversation_id}/summary` that aggregates counts (attachments, prompts) if it simplifies UI work.

## Must Read / Inspect
1. Task 06 output for the conversation schema.
2. Shared data layer repositories: `packages/shared_data_layer/repositories/conversations.py`, `.../documents.py`.
3. Existing pagination utilities or patterns in other routers (search `page_size` within `src/agent_api/http`).
4. Tests under `tests/http` for style patterns.

## Implementation Scope & Deliverables
- Add new endpoints to `conversations.py` and `documents.py` routers (or create dedicated modules if cleaner) implementing the queries above.
- Respect ownership/security: only return rows for the authenticated user. Enforce sensible max page sizes (e.g., 100) and default sorting (recent first).
- Support optional filters via query params; document them in Pydantic models for FastAPI docs.
- Update smoke CLI (and optionally docs) to use `GET /v1/conversations` when it needs to fetch existing sessions (e.g., verifying reset state) instead of calling the DB.
- Add tests covering pagination, filtering, unauthorized access, and no-results scenarios.
- Update the docs/runbooks to mention these endpoints so future UI tasks know they exist.

## Step-by-Step
1. Design response schemas (Pydantic) with metadata (pagination info, total count, list of items).
2. Implement repository/service queries with filters; ensure indexes exist or note follow-ups if needed.
3. Expose the endpoints via FastAPI router with dependency injection for auth + DB session.
4. Update CLI helpers to optionally fetch and print conversation/doc lists (useful for debugging).
5. Write unit tests for repository logic (if new) plus API tests for the endpoints.
6. Refresh documentation references + checklist; run QA suite.

## Definition of Done
- `/v1/conversations` and `/v1/documents` listing endpoints exist, fully tested, and wired into the app.
- CLI/docs leverage the new listings instead of assuming prior state.
- Pagination/filter semantics documented in both README/runbooks.

## Handoff Notes
- Capture any performance considerations (need for indexes, caching) so future tasks can address them.
- Note if additional filters (e.g., `status=COMPLETED`) are required by downstream UI work.
