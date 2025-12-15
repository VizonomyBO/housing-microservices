# Task 03 — Reduced E2E CLI Automation

## System Snapshot
- Task 02 introduced deterministic fixtures plus helper utilities for documents/prompts (`services/agent-api/tests/data/reduced_e2e/` and the loader module).
- No script yet ties auth registration, document uploads, attachments, and chat prompts together.
- Operators currently have to perform these flows manually via cURL or the FastAPI docs.

## What You Inherit
- Scenario plan (`docs/testing/reduced_e2e_smoke_plan.md`).
- Fixture loader module and tests from Task 02.
- Working auth + agent-api services reachable inside the Compose network when running `docker compose --profile reduced up`.

## Goal
Implement an automated CLI (Typer or argparse) that runs the entire reduced-profile workflow via HTTP calls. The tooling must live inside a dedicated Python module/package (e.g., `services/agent-api/scripts/reduced_e2e_smoke/`) so helpers can be shared across multiple entrypoints:
1. Register and log in a demo user (no email verification required).
2. Upload each Markdown fixture through `/v1/documents/upload`, waiting for the inline ingestion result.
3. Attach the uploaded documents to a conversation.
4. Issue all prompts in the scenario manifest against `/v1/chat` (covering blocking + streaming modes) and validate that answers cite the appropriate documents, include required keywords, and compute the expected aggregates.
5. Summarize the run (success/failure per step, response snippets, latency) as both console output and JSON (written to `logs/reduced_e2e_smoke.json`).

## Must Read / Inspect Before Coding
1. Fixture helper module created in Task 02.
2. Auth + Agent API route implementations and schemas (`services/auth-service/app/api/auth.py`, `services/agent-api/src/agent_api/http/routes/*.py`).
3. Streaming helpers (`services/agent-api/src/agent_api/http/streaming.py`) to understand SSE contracts.
4. LocalStack configuration in `.env.example` to know which env vars the script should honor (AWS credentials, buckets, etc.).

## Implementation Scope & Deliverables
- Create a package `services/agent-api/scripts/reduced_e2e_smoke/` with modules such as `fixtures.py`, `clients.py`, `validators.py`, and `cli.py`. The Typer app should live in `cli.py`, expose flags for base URLs/credentials/output paths, and import helpers rather than keeping all logic in one file.
- Provide an executable entry script (thin wrapper) or support `python -m services.agent_api.scripts.reduced_e2e_smoke.cli` plus a convenience shim under `services/agent-api/scripts/run_reduced_e2e_smoke.py` that simply calls into the module.
- Within the module:
  - Read fixtures/prompt metadata via the helper module.
  - Call the services via `httpx` (async or sync) with proper error handling/timeouts.
  - Automatically handle JWT capture (store access/refresh tokens) and set the required headers for Agent API calls.
  - Stream SSE responses when the prompt requires streaming, validating events as they arrive.
  - Validate each prompt using manifest rules (keywords, numeric totals, doc IDs) and record pass/fail reasons.
  - Write a machine-readable summary (JSON) plus human summary to stdout.
- Add unit/integration tests under `services/agent-api/tests/scripts/test_run_reduced_e2e_smoke.py` that mock HTTP responses (e.g., via `respx`) and cover success/failure paths.
- Update `pyproject.toml` test dependencies if needed (use `uv add --dev respx` or similar as part of the task if not already present).
- Update `epic-reduced-e2e/CHECKLIST.md` to mark Task 03 complete.

## Step-by-Step Instructions
1. Lay out the CLI structure (Typer app + dataclasses for run context, HTTP clients, validators).
2. Implement helper functions for:
   - User registration/login
   - Document upload + ingestion wait
   - Conversation attachment creation
   - Chat invocation (blocking + streaming)
   - Validation + reporting
3. Integrate LocalStack awareness (bucket names/endpoint) using env vars from `.env`/fixtures; fail fast if required env vars are missing.
4. Build unit tests that exercise each helper with mocked HTTP responses to avoid hitting real services.
5. Run the mandatory QA suite from `services/agent-api` (`uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`). Add targeted tests if needed.
6. Update the epic checklist and note any scope adjustments in Handoff Notes.

## Definition of Done
- CLI script + tests exist, pass lint/type/test gates, and align with the fixture manifest.
- Running `uv run python services/agent-api/scripts/run_reduced_e2e_smoke.py --help` (or `uv run python -m services.agent_api.scripts.reduced_e2e_smoke.cli --help`) prints clear usage instructions.
- JSON summary is written to `services/agent-api/logs/reduced_e2e_smoke.json` (path configurable), enabling later automation.

## Handoff Notes
- If the CLI reveals missing APIs or schema gaps, document them here and update Task 04 instructions accordingly so the Compose wrapper accounts for retries/ordering.
