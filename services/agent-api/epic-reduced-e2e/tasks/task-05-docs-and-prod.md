# Task 05 — Documentation & Production Compose Guide

## System Snapshot
- Tasks 01–04 produced the scenario plan, fixtures, automation CLI, and Compose wrapper + Make target for the reduced-profile E2E smoke.
- There is no centralized documentation describing how to run the new automation, nor guidance on running the platform in a production-style Compose mode (full profile, LocalStack or AWS toggles, secrets handling).
- README currently focuses on reduced/full development flows but lacks a “production mode” recipe.

## What You Inherit
- Plan + fixtures + CLI + wrapper from previous tasks.
- Existing runbooks (`docs/runbooks/reduced_scope_demo.md`, `docs/runbooks/full_stack_compose.md`).
- README sections on stack profiles.

## Goal
Document the new testing setup so any engineer can run it end-to-end, and expand the root README with explicit instructions for running the app in production mode using Compose (full profile + production-grade settings).

## Must Read / Inspect
1. `docs/testing/reduced_e2e_smoke_plan.md` (Task 01) and any updates from later tasks.
2. Wrapper script + Make target produced in Task 04.
3. README and runbooks to understand existing coverage.

## Implementation Scope & Deliverables
- Author `docs/testing/reduced_e2e_smoke.md` (or update the plan doc if you prefer a single source) that covers:
  - Purpose of the automation.
  - Prerequisites (Docker, LocalStack toggle, required env vars/API keys).
  - Step-by-step instructions for running the CLI directly and via the Compose wrapper/Make target.
  - Explanation of the fixtures, prompt validation, and how to interpret the JSON summary/logs.
  - Troubleshooting tips (auth failures, ingestion errors, LocalStack issues) and pointers to update the checklist when changes affect other tasks.
- Update `README.md` with a new section “Production Mode with Compose” describing how to run the full stack with production-like flags: copying `.env`, customizing secrets, using `STACK_PROFILE=full`, toggling `USE_LOCALSTACK`, binding to real AWS credentials, and invoking the Make target/wrapper as appropriate.
- Ensure documentation explicitly states that when a task intersects another’s scope, engineers must update `epic-reduced-e2e/CHECKLIST.md` (and any other relevant checklist) to keep automation deterministic.
- Mark this task complete in the checklist.

## Step-by-Step Instructions
1. Consolidate all knowledge gathered in Tasks 01–04 and outline the new doc.
2. Write the doc with clear sections: Overview, Prerequisites, Quick Start (CLI & wrapper), Validation Criteria, Troubleshooting, Updating the Epic.
3. Modify `README.md` to add the production Compose instructions (include commands, env var guidance, LocalStack vs AWS note, reference to new doc).
4. Optionally cross-link from `docs/runbooks/reduced_scope_demo.md` to the new doc.
5. Run the required QA commands before finalizing.
6. Delete your plan/tracker files and ensure git status is clean except for intentional changes.

## Definition of Done
- New/updated documentation clearly explains how to run the reduced E2E smoke automation and how to launch the platform in production mode via Compose.
- README contains a dedicated production-mode section referencing the new automation.
- Checklist marked complete; no TODOs left open.

## Handoff Notes
- Future adjustments to the automation (new prompts, different services) must update both `docs/testing/reduced_e2e_smoke_plan.md` and `docs/testing/reduced_e2e_smoke.md`, plus the checklist, to avoid diverging instructions.
- Task 04 added `scripts/run_reduced_e2e_compose.sh` + `make reduced-e2e-smoke`; document how `KEEP_STACK`, `ARGS="-- ..."`, and the `services/agent-api/logs/task_04/codex.log` output work so operators know where to inspect failures.
- If CI flakes on slow hosts, the wrapper exposes `MAX_HEALTH_ATTEMPTS` / `HEALTH_SLEEP_SECONDS` env vars—call that out when describing troubleshooting knobs.
