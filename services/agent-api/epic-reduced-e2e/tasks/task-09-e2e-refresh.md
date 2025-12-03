# Task 09 — E2E Automation Refresh (HTTP-only)

## System Snapshot
- Tasks 06–08 introduce the missing conversation lifecycle, reset, and listing endpoints.
- The smoke CLI still contains fallback logic for direct database inserts/resets and doesn’t validate the new endpoints end-to-end.
- Documentation references (scenario plan, smoke guide, README, runbooks) assume the earlier DB bootstrapper and need updates to reflect the all-HTTP workflow.

## What You Inherit
- Working HTTP endpoints for conversations, demo reset, and listings.
- Existing fixture loader + CLI package (`scripts/reduced_e2e_smoke/`) with structured reporting.
- Compose wrapper/Make target, docs from Task 05.

## Goal
Update the reduced E2E automation (code + docs) to exclusively use public HTTP endpoints. Remove all direct database manipulation from the smoke CLI, ensuring it behaves exactly like the intended web frontend. Outcomes:
1. CLI uses `/v1/conversations` POST to create sessions, `/v1/demo/*` for reset flows, `/v1/conversations` + `/v1/documents` GET for verification.
2. `DatabaseConversationBootstrapper` (and any helpers that bypass HTTP) are deleted or relegated to test-only utilities.
3. Documentation/tutorials reflect the new reality and highlight the REST-only path.

## Must Read / Inspect
1. Task 06–08 artifacts (routers, schemas, tests) so you understand expected payloads.
2. `scripts/reduced_e2e_smoke/runner.py`, `clients.py`, `bootstrap.py`, `validators.py` to map existing flows.
3. All smoke docs: `docs/testing/reduced_e2e_smoke_plan.md`, `docs/testing/reduced_e2e_smoke.md`, README sections referencing the CLI.

## Implementation Scope & Deliverables
- Refactor the CLI runner to drop `DatabaseConversationBootstrapper`; add HTTP client methods for the new endpoints (conversation create, demo reset, listings).
- Ensure configuration/env vars cover any new requirements (e.g., `DEMO_RESET=true`). Update Typer options + help text.
- Expand CLI tests (`tests/scripts/test_run_reduced_e2e_smoke.py`) to mock the new endpoints and assert they’re called in the correct order (reset → create conversation → upload docs → attach → chat → pillars → LocalStack).
- Update documentation (scenario plan, smoke guide, README, runbooks) to describe the new HTTP calls and remove references to direct DB access.
- Remove unused helper modules or flag them for deletion in Handoff Notes if needed elsewhere.

## Step-by-Step
1. Inventory all places where the CLI touches the database directly and plan replacements using the new HTTP helpers.
2. Implement HTTP client wrappers for the new endpoints (reuse `httpx` session + auth headers) and plug them into the runner sequence.
3. Delete or deprecate the bootstrap helper; update tests accordingly.
4. Update docs (plan + execution guide + README) to describe the REST-only workflow, including reset/listing steps.
5. Run QA suite and fix any regressions.
6. Update the epic checklist and note any remaining gaps for future tasks.

## Definition of Done
- Smoke CLI performs the entire workflow via HTTP endpoints; no direct DB imports remain.
- Unit tests reflect the new flows and pass along with the QA suite.
- Documentation and runbooks are up to date, and operators know how to trigger resets/listings.

## Handoff Notes
- If further improvements (e.g., UI scaffolding) are needed, document them here for future epics.
- Call out any new environment variables or flags introduced while removing the DB bootstrapper.
