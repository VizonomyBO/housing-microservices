# Reduced E2E Smoke Execution Guide

This guide describes how to run the reduced-profile end-to-end smoke automation that ships with Epic 3.5. Pair it with the scenario plan in `docs/testing/reduced_e2e_smoke_plan.md` whenever you need deeper context on fixtures, prompts, and validation criteria.

## Overview
- **Purpose**: Verify that registration, authentication, deterministic HTTP conversation bootstrap, document ingestion, attachment, prompt validation, pillars, and LocalStack health checks all succeed when the stack runs with `STACK_PROFILE=reduced` (no direct DB writes from the CLI).
- **Entrypoints**: Typer CLI (`scripts/run_reduced_e2e_smoke.py`) and the Compose wrapper (`scripts/run_reduced_e2e_compose.sh`, surfaced as `make reduced-e2e-smoke`).
- **Outputs**: Structured JSON summary at `services/agent-api/logs/reduced_e2e_smoke.json` (or `/app/logs/reduced_e2e_smoke.json` when running inside the container) plus mirrored console output in `services/agent-api/logs/task_04/codex.log` when using the wrapper.
- **Inventory checkpoints**: The CLI now surfaces `/v1/conversations` and `/v1/documents` listings before and after uploads so you can prove that document counts and hashes match what the API exposes (no manual SQL needed).
- **Real-tool verification**: When `--use-real-tools` is set, the CLI performs a lightweight pre-flight `/v1/documents` probe plus a post-run verification stage that inspects `X-Cache-Mode`, `Viz-Demo-Mode`, and `X-RateLimit-Policy` headers. Toggle enforcement with `--verify-real-tools/--skip-verify-real-tools` or `REDUCED_E2E_VERIFY_REAL_TOOLS`; failures indicate the backend never left text-only mode.
- **Telemetry**: Real-tool runs capture HTTP call latency samples and real-tool counters (ingestion jobs, reranker prompts) in the `telemetry` block of the JSON report so reviewers can prove OpenAI/Voyage were exercised.
- **When to update**: Any time fixtures, prompts, scripts, or Compose profiles change, update this guide, the scenario plan, and `epic-reduced-e2e/CHECKLIST.md` before handing the work off.
- **No stubs**: Smoke/e2e runs must exercise the real LangGraph runner, ingestion pipeline, and external APIs. Flip `REDUCED_SCOPE_USE_REAL_TOOLS=1` (or export `REAL_REDUCED_E2E_TOOLS=1` / pass `--use-real-tools`) whenever you need OpenAI/Voyage coverage—the service now refuses to start without `OPENAI_API_KEY` + `VOYAGE_API_KEY`. The only temporary exceptions are Valkey/cache wiring and image/table ingestion, and unit tests may still patch their clients. If a run reports reduced-scope stubs or fake services, treat it as a failure.
- **Authentication**: The CLI always registers/logs in via auth-service and forwards the returned JWT. Manual API calls must now include `Authorization: Bearer <token>` or they’ll fail with `401`.

## Prerequisites
1. **Tooling**: Docker 25.x with Compose V2 (`docker compose`), Git, a POSIX-compatible shell, and [uv](https://github.com/astral-sh/uv) (Python 3.13) for running the CLI.
2. **Environment files**: From the repo root:
   ```bash
   cp env.example .env            # populate secrets/ports before first run
   touch .env.local && chmod 600 .env.local  # optional developer overrides
   ```
   - Define `STACK_PROFILE=reduced`, `COMPOSE_PROFILES=reduced`, `SERVICE_MODE=reduced`, and `USE_LOCALSTACK=1` (default) for the smoke workflow.
   - No direct database connection is required for the smoke CLI anymore; all bootstrap/reset steps use public HTTP endpoints.
  - For real-tool runs, set `REDUCED_SCOPE_USE_REAL_TOOLS=1` (or rely on `REAL_REDUCED_E2E_TOOLS=1`/`--use-real-tools`) **and** provide `OPENAI_API_KEY` + `VOYAGE_API_KEY` in `.env` or `.env.local`. The Compose wrapper refuses to start the stack when those secrets are missing.
   - Keep `AUTH_SHARED_SECRET` in sync with `JWT_SECRET_KEY` (and leave `AUTH_JWKS_URL` empty) until auth-service exposes a JWKS endpoint; this lets the Agent API validate the JWTs returned by auth-service.
3. **LocalStack vs AWS**:
   - When `USE_LOCALSTACK=1`, export `AWS_ENDPOINT_URL=http://localhost.localstack.cloud:4566` so the automation validates mock AWS endpoints.
   - When targeting AWS, set `USE_LOCALSTACK=0`, clear `AWS_ENDPOINT_URL`, and supply `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN` via `.env.local`.
4. **Access & ports**: Ensure ports `8000`, `5001`, `5002`, and `4566` are free. Override them in `.env` if another process is bound.

## Key Artifacts
| Path | Description |
| --- | --- |
| `scripts/run_reduced_e2e_smoke.py` | Launches the Typer CLI (`scripts/reduced_e2e_smoke/cli.py`). |
| `scripts/run_reduced_e2e_compose.sh` | Wrapper that copies `.env`, starts the reduced Compose profile, probes health endpoints, runs the CLI inside `agent-api`, and tears everything down (unless `KEEP_STACK=1`). |
| `Makefile` (`reduced-e2e-smoke` target) | Thin wrapper that executes the script above from the repo root and forwards `ARGS`. |
| `scripts/reduced_e2e_fixtures.py` + `tests/data/reduced_e2e/*` | Scenario manifest and markdown docs for policy memo, ledger, and KPI table fixtures. |
| `scripts/reduced_e2e_smoke/` | Bootstrap helpers, HTTP clients, prompt validators, and reporting utilities used by the CLI. |
| `services/agent-api/logs/task_04/codex.log` | Rolling log captured by the Compose wrapper (timestamps, health checks, CLI output). |

## Quick Start Options

### Option A — Run the CLI Directly (stack already running)
1. Launch the reduced profile stack using the runbook (`docs/runbooks/reduced_scope_demo.md`) or manually:
   ```bash
   STACK_PROFILE=reduced \
   COMPOSE_PROFILES=reduced \
     docker compose --profile reduced up --build agent-api auth-service user-service localstack
   ```
2. From `services/agent-api`, activate the virtual environment (`uv venv --python 3.13 .venv` once, then rely on `uv run`).
3. Invoke the CLI:
   ```bash
   cd services/agent-api
   uv run python scripts/run_reduced_e2e_smoke.py run \
     --report-path logs/reduced_e2e_smoke.json \
     --reseed-docs
   ```
   - Provide overrides such as `--skip-pillars`, `--timeout-seconds 45`, or `--stream-capability cross_doc_reasoning --stream-capability sql_reasoning` as needed.
   - When `USE_LOCALSTACK=1`, include `--localstack-url http://localhost.localstack.cloud:4566` (or point it at whatever endpoint Docker exposes). Skip the flag entirely when targeting real AWS so the LocalStack probe stage is omitted.
   - Pass `--use-real-tools` (or export `REAL_REDUCED_E2E_TOOLS=1`) whenever the stack is running with `REDUCED_SCOPE_USE_REAL_TOOLS=1` so the CLI records a real-tool run.
   - Use `--verify-real-tools/--skip-verify-real-tools` (env: `REDUCED_E2E_VERIFY_REAL_TOOLS`) to control whether the CLI fails when headers still report text-only mode. This defaults to `--verify-real-tools` whenever you pass `--use-real-tools`.
   - Pass `--reseed-docs` (default in the example above) to invoke the demo reset endpoints before uploads; combine with `--cleanup-only` when you just need to wipe demo state without executing prompts.
   - All CLI parameters have matching env vars (see `scripts/reduced_e2e_smoke/cli.py`). Running with `env REDUCED_E2E_EMAIL=... uv run python ...` keeps sensitive values out of shell history.
4. Inspect the summary:
   ```bash
   jq '.' logs/reduced_e2e_smoke.json
   ```
   - Expect new stages named `conversation_inventory`, `document_inventory`, and `conversation_documents_synced`; each stage logs the payload returned by `/v1/conversations` or `/v1/documents` so you can confirm resets and attachment counts without cracking open Postgres.

### Option B — One-command Wrapper via Make
1. From the repo root, run:
   ```bash
   make reduced-e2e-smoke ARGS="--skip-pillars"
   ```
2. Important environment knobs (export before invoking the target):
   | Variable | Purpose |
   | --- | --- |
   | `ARGS="--timeout-seconds 60 --verbose-http"` | Forwards CLI flags to `scripts/run_reduced_e2e_smoke.py`. |
   | `REAL_REDUCED_E2E_TOOLS=1` | Propagates `REDUCED_SCOPE_USE_REAL_TOOLS=1` into the containers and passes `--use-real-tools` / env mirrors to the CLI (requires `OPENAI_API_KEY` + `VOYAGE_API_KEY`). |
   | `REDUCED_E2E_VERIFY_REAL_TOOLS=1` | Forces the CLI to keep verification enabled even if you pass `ARGS="--skip-verify-real-tools"`; set to `0` to allow instrumentation without failing the run. |
   | `KEEP_STACK=1` | Leaves Docker containers running for post-mortem inspection. Default tears down the stack. |
   | `FORCE_ENV_COPY=1` | Replaces `.env` with `env.example` before starting Compose (useful in CI). |
   | `REDUCED_E2E_RESEED_DOCS=1` | Forces the CLI to call demo reset + purge endpoints before uploads without passing extra CLI flags. |
   | `REDUCED_E2E_CLEANUP_ONLY=1` | Runs the HTTP cleanup stages and exits before uploads/prompts (mirrors `--cleanup-only`). |
   | `MAX_HEALTH_ATTEMPTS` / `HEALTH_SLEEP_SECONDS` | Adjust health-check retries while waiting on Agent API, auth-service, user-service, and LocalStack. |
   | `CLI_REPORT_PATH=/app/logs/reduced_e2e_smoke.json` | Override report path inside the container. |
   | `ARGS="--reseed-docs"` | Forces the CLI to call the demo reset endpoints before uploading fixtures. |
   | `ARGS="--cleanup-only"` | Runs the demo cleanup endpoints and exits without executing uploads/prompts. |
   | `CLI_PYTHONPATH` | Extend module search paths if you move scripts. |
   - The wrapper mirrors `USE_LOCALSTACK`: set `USE_LOCALSTACK=0` to skip the LocalStack container and probe stage so the CLI points directly at AWS; leave it at `1` to keep the mock endpoints online.
3. Logs stream to `services/agent-api/logs/task_04/codex.log`. Use `tail -f services/agent-api/logs/task_04/codex.log` for live triage.
4. Wrapper behavior recap:
   - Copies `.env` (unless already present or `FORCE_ENV_COPY` toggled).
   - Forces `COMPOSE_PROFILES` to include `reduced` and `aws-mock` so LocalStack is available.
   - Starts `postgres`, `db-init`, `agent-api`, `auth-service`, `user-service`, and `localstack` in detached mode, waits for `/health` endpoints, then runs the CLI inside the `agent-api` container via `uv run`.
   - Tears down containers unless `KEEP_STACK=1`.

## Cleanup & Reseed Workflow
- The Agent API exposes `/v1/demo/reset-conversation` (detaches documents, clears chat history/checkpoints) and `/v1/demo/purge-documents` (removes uploaded fixture docs for the authenticated user). These routes only exist when `SERVICE_MODE=reduced`.
- Passing `--reseed-docs` (or setting `ARGS="--reseed-docs"` in the Make wrapper) calls both endpoints immediately after the CLI bootstraps a conversation so re-runs never hit dedupe errors.
- `--cleanup-only` performs register/login, invokes the demo endpoints, writes the JSON summary, and exits without uploading fixtures or running prompts—handy for CI resets between runs without dropping the database.
- Both flags derive alias/hash lists from `ScenarioFixtures`, so new fixture aliases automatically flow into the purge payload without manual updates.
- After the cleanup stages run, the CLI immediately hits `/v1/conversations` and asserts that `document_count=0` for the deterministic conversation; if that check fails, investigate attachments instead of attempting manual SQL cleanups.

## Reports, Logs, and Validation
- **JSON summary**: `logs/reduced_e2e_smoke.json` captures `scenario`, `version`, `stages`, `prompts`, and `success`. Each stage lists latency, metadata (user IDs, conversation IDs, number of uploads), and any failure details. Archives live under the same directory if you specify alternate paths. When `--use-real-tools` is active, the JSON also includes `telemetry.real_tools` (verification result, embedding job count, reranker prompt count) and `telemetry.http_calls` (latency samples) so reviewers can prove the run touched OpenAI/Voyage.
- **Inventory metadata**: `conversation_inventory`, `document_inventory`, and `conversation_documents_synced` stages now persist the exact payloads returned by `/v1/conversations` and `/v1/documents` (counts, hashes, aliases). Reference these fields when validating cleanup or diagnosing attachment drift.
- **Structured console output**: The CLI prints PASS/FAIL tables with ✅ / ❌ indicators. When run via the wrapper, this output is mirrored to `logs/task_04/codex.log`.
- **Fixture manifest**: `tests/data/reduced_e2e/scenario_manifest.json` enumerates document aliases (DOC_POLICY, DOC_LEDGER, DOC_KPI) plus prompt IDs (`Q_SIMPLE_QA`, `Q_REASON`, `Q_AGGREGATE`, `Q_SQL`). Update both the manifest and this doc whenever you add or remove fixtures.
- **Prompt validators**: `scripts/reduced_e2e_smoke/validators.py` houses regex and numeric checks (e.g., `$7.35M` sum, Harbor City KPI 87). If prompts change, adjust the validator and describe the new expectations within this guide.

## Mode Matrix – Text-only vs Real Tooling
| Mode | How to enable | LLM / embeddings | Cache & rate limiting | Required secrets |
| --- | --- | --- | --- | --- |
| **Text-only (default)** | Leave `REDUCED_SCOPE_USE_REAL_TOOLS=0` (wrapper env var unset) | LangGraph sticks to text-only chunks, auto-completes ingestion jobs, and skips OpenAI/Voyage calls. | Valkey client + rate limiter remain disabled (`InMemory` + demo headers). | None beyond LocalStack defaults.
| **Real tooling** | Set `REDUCED_SCOPE_USE_REAL_TOOLS=1` in `.env` *or* export `REAL_REDUCED_E2E_TOOLS=1`/pass `--use-real-tools` when using the CLI or Compose wrapper. | LangGraph must call OpenAI + Voyage; text-only guardrails lift so ingestion behaves like production. | Cache + limiter wiring re-enable (Valkey stub allowed, but demo shims disabled). | `OPENAI_API_KEY` and `VOYAGE_API_KEY` must be present; startup fails fast if either is missing.

## Troubleshooting
| Symptom | Suggested Action |
| --- | --- |
| `register` stage fails with 409 | Previous run already seeded the demo email. Use a new `REDUCED_E2E_EMAIL` **or** run the CLI with `--reseed-docs` / `--cleanup-only` to invoke `/v1/demo/reset-conversation` + `/v1/demo/purge-documents` before uploads—no DB tear-down required. |
| CLI re-runs hit dedupe failures | Export `REDUCED_E2E_RESEED_DOCS=1` (or pass `--reseed-docs`) so the HTTP demo reset + purge endpoints run before uploads; combine with `REDUCED_E2E_CLEANUP_ONLY=1` when you just want cleanup. |
| LocalStack stage times out | Confirm `USE_LOCALSTACK=1`, port 4566 is free, and `AWS_ENDPOINT_URL` matches `http://localhost.localstack.cloud:4566`. Increase `MAX_HEALTH_ATTEMPTS`/`HEALTH_SLEEP_SECONDS` for slow hosts. |
| Attachments missing after uploads | Inspect `logs/reduced_e2e_smoke.json` for the `attach_documents` metadata. If dedupe prevented uploads, delete existing attachments via the Agent API or rerun with a fresh conversation UUID. |
| Pillar validation flakes | Temporarily pass `--skip-pillars` (or `ARGS="--skip-pillars"`) while investigating. Capture failures in `logs/task_04/codex.log` and update validators only after confirming backend changes. |
| Real-tool verification fails | Inspect the `real_tool_verification` stage detail plus `telemetry.real_tools` to see which headers stayed in text-only (`X-Cache-Mode=text-only`, `X-RateLimit-Policy=demo-mode`). Ensure `REDUCED_SCOPE_USE_REAL_TOOLS=1`, `OPENAI_API_KEY`, and `VOYAGE_API_KEY` are exported inside the containers, then rerun with `--verify-real-tools`. |
| Compose wrapper exits early when REAL_REDUCED_E2E_TOOLS=1 | The wrapper now enforces that `OPENAI_API_KEY` and `VOYAGE_API_KEY` exist before starting Docker. Populate them in `.env`/`.env.local` or unset `REAL_REDUCED_E2E_TOOLS`. |

## Checklist Hygiene & Handoff Expectations
- Whenever you add new stages, fixtures, or troubleshooting steps, immediately update:
  1. `docs/testing/reduced_e2e_smoke_plan.md` (source-of-truth scenario doc).
  2. `docs/testing/reduced_e2e_smoke.md` (this run guide).
  3. `services/agent-api/epic-reduced-e2e/CHECKLIST.md` (mark completed items, insert follow-ups, and capture dates/notes).
- Note significant deltas in the “Handoff Notes” section of any downstream task files to prevent duplicated effort.

For escalations, cross-reference the reduced and full stack runbooks (`docs/runbooks/reduced_scope_demo.md`, `docs/runbooks/full_stack_compose.md`) and link relevant log excerpts in your PR or issue.
