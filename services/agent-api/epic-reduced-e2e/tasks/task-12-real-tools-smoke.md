# Task 12 — Real-Tools Smoke Automation & Verification

## System Snapshot
- Tasks 10–11 enable real tooling and wire LangGraph to OpenAI/Voyage, but the smoke CLI/tests still assume text-only behavior.
- Compose wrapper does not validate that the backend actually flipped into real-tool mode; failures could silently fall back to stubs.
- Documentation/runbooks focus on the reduced-mode workflow and lack guidance for exercising real models safely (cost limits, rate limits, retries).

## What You Inherit
- HTTP automation stack, CLI, and docs from Tasks 01–09.
- New configuration/runner work from Tasks 10–11.
- `.env` entries for OpenAI/Voyage secrets.

## Goal
Update the smoke automation so operators (local + CI) can deliberately run the scenario against real OpenAI/Voyage services, while keeping AWS mocked via LocalStack. Deliverables:
1. CLI flag/env var (`--verify-real-tools` or reuse `--use-real-tools`) that asserts backend headers/report metadata prove real mode is active.
2. Optional pre-flight check that calls a lightweight `/v1/internal/self-test` (or similar) to confirm keys are valid before the expensive run.
3. Enhanced reporting (JSON + console) clearly stating when real tools were used and how much latency/cost accrued.
4. Docs/runbooks covering the workflow, safeguards, and rollback instructions.

## Must Read / Inspect
1. `scripts/reduced_e2e_smoke/runner.py` and tests to understand current stages.
2. `scripts/run_reduced_e2e_compose.sh` + Make target details.
3. `docs/testing/reduced_e2e_smoke.md` + runbook for command references.

## Implementation Scope & Deliverables
- Extend Typer CLI + `SmokeRunConfig` with `use_real_tools` + `verify_real_tools` flags (env mirrors) that:
  - Trigger the new settings introduced in Task 10.
  - Inspect `/v1/chat` and `/v1/documents` responses for headers/metadata proving real mode is active (e.g., `X-Cache-Mode: standard`, `Viz-Demo-Mode: standard`) and assert no runtime stubs are in play (fail when the backend reports reduced-scope shortcuts).
- Update the runner to record additional telemetry (latency per external call, number of embeddings/reranker hits) when real mode is active; surface in JSON report so reviewers can prove the run hit real services instead of stubs.
- Add a pre-flight stage (optional) that hits a new internal endpoint or issues a short chat/embedding request to ensure secrets work; fail early with actionable messaging.
- Teach `scripts/run_reduced_e2e_compose.sh` to accept `REAL_REDUCED_E2E_TOOLS=1` (or similar) and refuse to start unless required secrets exist.
- Strengthen tests:
  - respx mocks verifying `use_real_tools` toggles additional HTTP calls/headers.
  - CLI unit tests ensuring verification fails when backend stays in text-only mode.
  - Docs-lint or sample command snippet demonstrating both modes.
- Refresh docs (`docs/testing/reduced_e2e_smoke_plan.md`, `docs/testing/reduced_e2e_smoke.md`, README runbook section) with new instructions, cautionary notes about key usage, and troubleshooting.

## Step-by-Step Instructions
1. Update CLI config objects + Typer flags; propagate to runner + HTTP clients.
2. Implement verification logic (e.g., new stage `real_tool_validation`).
3. Extend Compose wrapper to export the flag and check env secrets.
4. Add/adjust tests for CLI/respx flows.
5. Run QA suite; optionally perform a manual real-tool smoke run (document output location, cost, etc.).
6. Document workflow changes and update the epic checklist.

## Definition of Done
- Operators can intentionally run the reduced smoke scenario against real OpenAI/Voyage services with a single flag.
- Automation fails fast when secrets are missing or the backend fails to enable real mode.
- JSON report + console output clearly indicate whether real tools were exercised.
- Docs/runbooks explain the procedure, safeguards, and rollback.

## Handoff Notes
- Capture any rate-limit/cost observations so future epics can implement quotas or scheduled jobs.
- Note open questions about multi-tenant secrets or CI key rotation if they surface during validation.
