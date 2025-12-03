# Task 06 — Conversation Lifecycle HTTP Endpoint

## System Snapshot
- Smoke automation currently inserts conversations directly into Postgres via `DatabaseConversationBootstrapper` because the public API lacks a conversation create/read flow.
- Attachments (`/v1/conversations/{id}/attachments`) and chat (`/v1/chat`) require a valid conversation ID, which forces any frontend-like client to have out-of-band privileges.
- Reduced profile auth already issues JWTs through `auth-service`; every new HTTP entrypoint must reuse that contract.

## What You Inherit
- Stable auth/login endpoints under `auth-service` plus the fastapi app, rate limiter, and shared data layer repositories already in use by existing routes.
- Pydantic schemas and HTTP helpers for attachments/pillars that you can mirror for request/response validation.
- End-to-end smoke CLI + tests that expect to bootstrap a conversation before uploads.

## Goal
Expose authenticated HTTP endpoints for creating and fetching reduced-scope conversations so any automation (or future UI) can drive the entire workflow through the public API surface. At a minimum:
1. `POST /v1/conversations` — creates (or idempotently reuses) a conversation for the authenticated user, taking an optional `title`, `country_code`, `tags`, and deterministic namespace slug.
2. `GET /v1/conversations/{conversation_id}` — returns metadata for a single conversation the user owns.
3. Properly wires into the shared data layer, emits audit logging, and enforces rate limits.

## Must Read / Inspect Before Coding
1. `src/agent_api/http/routes/attachments.py` and `chat.py` for router structure, deps (`get_auth_context`, `get_request_context`, etc.).
2. `scripts/reduced_e2e_smoke/bootstrap.py` for the deterministic UUID logic you’ll migrate into the new endpoint.
3. Shared data layer models (`packages/shared_data_layer/db/models/conversations.py`) to ensure schema alignment.
4. `tests/http` suites to follow existing testing style (TestClient + dependency overrides).

## Implementation Scope & Deliverables
- Add a new router module (e.g., `src/agent_api/http/routes/conversations.py`) registered in `src/agent_api/http/routes/__init__.py` or the FastAPI app wiring.
- Implement POST + GET endpoints using async SQLAlchemy sessions and the shared data layer conversation repository. Support an optional `namespace` parameter that defaults to `"reduced-e2e"` and reuses the uuid5 logic from the bootstrap helper.
- Ensure responses include `conversation_id`, `owner_user_id`, `country_code`, `title`, `created_at`, and any metadata tags.
- Update auth context/permissions so non-owners receive 404/403 and requests without JWTs return 401.
- Replace the direct database bootstrapper in the smoke CLI with a client that hits the new endpoint (keep the helper for now but route it through HTTP; Task 09 will complete the cleanup).
- Add unit/integration tests under `tests/http/conversations/` (or similar) plus smoke CLI tests mocking the new HTTP call.
- Update `docs/testing/reduced_e2e_smoke_plan.md` to mention the new endpoint in the scenario matrix.

## Step-by-Step Instructions
1. Re-read the must-read files and sketch request/response models (Pydantic) for create + read.
2. Implement the repository/service helper that encapsulates the uuid5/idempotent insert, then expose it through the FastAPI router with proper dependency injection.
3. Wire the router into the main app configuration so `/v1/conversations` is available under both reduced and full profiles.
4. Update the smoke CLI to call the HTTP endpoint (via `httpx`) instead of directly importing the bootstrap helper; keep backward compatibility flag until Task 09.
5. Write unit tests for the router (fixtures for auth context, DB session) covering success, existing conversation reuse, unauthenticated requests, and cross-user access.
6. Extend CLI tests to ensure the new HTTP call is invoked and failure surfaces are captured.
7. Run the required QA suite from `services/agent-api` (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`).
8. Update `epic-reduced-e2e/CHECKLIST.md` (mark Task 06 complete when done) and note any follow-ups.

## Definition of Done
- POST + GET conversation endpoints exist, enforce auth/rate limits, and reuse shared data layer models without direct DB access from clients.
- Smoke CLI can create conversations via HTTP when pointed at the reduced stack.
- Tests cover happy path + access control. QA suite passes.
- Docs/checklist updated with the new workflow.

## Handoff Notes
- If you discover additional fields needed by the frontend (e.g., last message timestamp), document them here so Task 07/08 can incorporate them.
- Keep the deterministic namespace behavior because downstream scripts rely on stable IDs; note any intentional deviations in the checklist.
- POST/GET `/v1/conversations` now surface `namespace`, `tags`, and `created` flags. The smoke CLI defaults to the HTTP bootstrapper (`HttpConversationBootstrapper`) but still exposes the DB helper for explicit overrides. Future tasks (07–09) should reuse the HTTP client helpers in `scripts/reduced_e2e_smoke/clients.py` instead of importing shared_data_layer directly.
