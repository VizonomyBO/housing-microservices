# Task 01 — Reduced Stack E2E Test Plan

## System Snapshot
- We can launch the reduced Agent API profile plus LocalStack via the root `docker-compose.yml`, but there is no automation that simulates a real frontend session end-to-end.
- Existing smoke coverage (`services/agent-api/scripts/verify_reduced_scope_compose.sh`) only validates Compose config + a handful of FastAPI tests; it never exercises auth, document upload, attachments, or chat endpoints together.
- Documentation (README, runbooks) describes manual steps but not a deterministic scenario with canned documents, prompts, and acceptance checks.

## What You Inherit
- Compose stack + runbooks under `docs/runbooks/reduced_scope_demo.md` and `docs/runbooks/full_stack_compose.md`.
- HTTP route implementations for auth (`services/auth-service/app/api/auth.py`) and Agent API upload/chat routers (`services/agent-api/src/agent_api/http/routes/`).
- Prior assessment from the user describing desired automation (user registration, document uploads, attachments, multi-capability chat prompts referencing LocalStack-backed docs).

## Goal
Author a research-backed plan for the reduced-profile E2E automation. The plan must define:
- Scenario narrative (user persona, uploaded documents, conversation flow) and why each step validates a unique capability (doc QA, reasoning, aggregates, SQL-style questions).
- Required data fixtures (Markdown docs, prompts, expected response characteristics, document IDs to cite).
- Technical design: where the automation script will live, how it authenticates, how it talks to LocalStack, and how it validates results.
- Supporting infrastructure needed in later tasks (helper modules, CLI entry point, Compose wrapper, docs).
Capture all of this in a new planning doc so future tasks can implement without rediscovering context.

## Must Read / Inspect Before Writing
1. `docs/runbooks/reduced_scope_demo.md` and `docs/runbooks/full_stack_compose.md`.
2. `README.md` sections on stack profiles and seeding.
3. Auth + Agent API HTTP routes for `/v1/auth/register`, `/v1/auth/login`, `/v1/documents/upload`, `/v1/conversations/{id}/attachments`, `/v1/chat`.
4. `services/agent-api/scripts/verify_reduced_scope_compose.sh` for current smoke coverage.
5. User-provided requirements in the latest chat transcript (attach docs, run LocalStack, cover every chat mode).

## Implementation Scope & Deliverables
- Create `docs/testing/reduced_e2e_smoke_plan.md` that includes:
  - Narrative scenario + table of steps (user registration, login, uploads, attachments, chat prompts) tied to specific APIs.
  - Detailed data requirements for at least three documents (policy memo, financial ledger, structured table) and the prompt/answer expectations for: simple QA, propositive reasoning, numerical aggregate, SQL-style grouping.
  - Technical architecture of the upcoming automation: script location (`services/agent-api/scripts/run_reduced_e2e_smoke.py`), dependency graph, LocalStack usage, configuration (env vars, secrets), and success/failure reporting.
  - Validation strategy (commands to run, expected Compose profiles, how to identify failures) and risks/open questions.
- Update `epic-reduced-e2e/CHECKLIST.md` to mark Task 01 complete once finished.

## Step-by-Step Instructions
1. Re-read the files listed above and capture relevant constraints/assumptions.
2. Research any missing pieces (e.g., best practices for scripting LocalStack-backed S3 uploads) via Context7/web and cite links in the plan.
3. Draft the plan document with clearly labeled sections: Overview, Scenario Matrix, Data Fixtures, Automation Architecture, Validation Strategy, Risks & Follow-ups.
4. Ensure the plan states how later tasks should update the checklist if they skip or consolidate scope.
5. Run the standard verification commands from `services/agent-api` even though this task is documentation-only (per AGENT rules, keep repo clean).
6. Update the epic checklist entry for Task 01 and remove your plan/tracker files before finishing.

## Definition of Done
- `docs/testing/reduced_e2e_smoke_plan.md` exists with the required sections, citations, and actionable guidance for Tasks 02–05.
- Any new insights affecting downstream tasks are reflected in this task file’s Handoff Notes or the checklist.
- QA commands succeed and no unrelated files remain modified.

## Handoff Notes
- Future tasks must follow the data + prompt specs from the new plan; if changes become necessary, update the plan and this checklist immediately to prevent duplicate or conflicting work.
- 2025-12-03: `docs/testing/reduced_e2e_smoke_plan.md` now defines three markdown documents (policy memo, ledger, KPI table), four prompt families, deterministic conversation UUID logic, and LocalStack health probes. Task 02 must implement fixtures/helpers that match those specs (including conversation bootstrap helper); update this file + checklist if you add/remove documents or prompt categories.
