# Task 02 — Scenario Fixtures & Helper Modules

## System Snapshot
- Task 01 documented the reduced-profile E2E scenario, including document themes, prompt matrix, and automation architecture (`docs/testing/reduced_e2e_smoke_plan.md`).
- No reusable fixtures currently exist for those documents or prompts; engineers would need to handcraft payloads each time.
- The automation script will need deterministic inputs (Markdown files, prompt metadata, expected assertions) and lightweight helper functions to load them.

## What You Inherit
- Plan document from Task 01 (required reading) describing doc contents and question types.
- Existing sample data under `services/agent-api/tests/data/` that you can use as reference for directory layout and naming.
- Reduced-scope ingestion helpers (e.g., `services/agent-api/scripts/seed_reduced_scope_data.py`) that show how markdown/text content is handled.

## Goal
Create reusable fixtures for the reduced E2E smoke scenario and helper modules the upcoming CLI can import. The assets must cover:
- Markdown documents (at least three) matching the narratives defined in Task 01 (policy memo, ledger, structured summary, etc.).
- JSON/YAML metadata describing associated prompts, expected answer hints, and which document each prompt should cite.
- Python helper(s) that load the fixtures, hash contents, and provide typed accessors for the automation script.

## Must Read / Inspect Before Coding
1. `docs/testing/reduced_e2e_smoke_plan.md` (Task 01 output).
2. `services/agent-api/tests/data/*` for precedent on storing fixtures.
3. `services/agent-api/src/services/` modules that currently handle document uploads to understand required payload fields.

## Implementation Scope & Deliverables
- Create a new fixture directory: `services/agent-api/tests/data/reduced_e2e/` containing:
  - Markdown files for each document described in the plan (include explanatory front-matter or inline headings for readability).
  - A scenario manifest (JSON or YAML) that lists prompts, question types, required citations/document IDs, and validation rules (e.g., keywords expected in responses, numerical totals to check).
- Add a helper module (e.g., `services/agent-api/scripts/reduced_e2e_fixtures.py`) that:
  - Loads fixtures from disk.
  - Exposes Pydantic models/dataclasses for documents and prompts.
  - Computes SHA-256 hashes so the automation can assert deduplication behavior.
- Include unit tests under `services/agent-api/tests/scripts/test_reduced_e2e_fixtures.py` validating file loading, schema parsing, and hash stability.
- Update `epic-reduced-e2e/CHECKLIST.md` to mark Task 02 complete.

## Step-by-Step Instructions
1. Review the plan doc and distill exact document/prompt requirements.
2. Author the Markdown files and scenario manifest inside the new fixture directory.
3. Implement the helper module with clear docstrings and minimal dependencies (stick to stdlib + existing repo packages).
4. Write tests covering fixture parsing, validation, and any utility functions.
5. Run the standard QA suite (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`).
6. Update this task’s entry in the epic checklist; note any deviations in the Handoff Notes below.

## Definition of Done
- Fixtures + manifest exist under `services/agent-api/tests/data/reduced_e2e/` and match the scenario plan.
- Helper module + tests give future tasks a stable API for loading those fixtures.
- QA commands pass; plan/tracker files removed.

## Handoff Notes
- If you modify the scenario relative to Task 01, update `docs/testing/reduced_e2e_smoke_plan.md` and mention the change in the checklist so Task 03 can rely on the new truth.
- 2025-12-03: Fixtures + manifest now live under `tests/data/reduced_e2e/`, and `scripts/reduced_e2e_fixtures.py` exposes Pydantic models plus hashing helpers. Task 03 should import `FixtureLoader` instead of re-reading YAML/markdown manually; scenario contents still match `docs/testing/reduced_e2e_smoke_plan.md`.
