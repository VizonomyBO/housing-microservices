# Task 10 — Real Tooling Mode & Env Hardening

## System Snapshot
- The reduced E2E workflow currently runs entirely in “text-only” mode: LangGraph skips OpenAI calls, embeddings/reranker are stubbed, and Valkey/rate limiting stay disabled.
- Operators can set secrets in `.env`, but the service never consumes them during smoke runs, making it impossible to validate production tooling.
- Compose wrapper copies `env.example` when missing, yet there is no guardrail to ensure real-model prerequisites exist before attempting a “full fidelity” run.

## What You Inherit
- Fully working HTTP endpoints (Tasks 06–09) and automation scripts for text-only verification.
- Environment plumbing via `Settings`/`ReducedScopeSettings`, plus Compose/Make wrappers.
- Documentation describing the reduced-mode workflow (`docs/testing/reduced_e2e_smoke.md`).

## Goal
Introduce an explicit “real tooling” mode that keeps AWS mocked via LocalStack but uses actual OpenAI + Voyage services. Outcomes:
1. Config flags/env vars that disable every runtime stub (LLM, ingestion auto-complete, fake rate limits) except the explicitly allowed exceptions (Valkey/cache, image/table ingestion) so the smoke stack mirrors production.
2. Startup validation that fails fast when required secrets are missing for real tooling runs.
3. Compose + CLI switches that let operators choose between text-only and real-tool modes without editing code.

## Must Read / Inspect
1. `src/agent_api/settings.py` and `src/agent_api/reduced_scope.py` for flag definitions.
2. `scripts/run_reduced_e2e_compose.sh` + `docs/testing/reduced_e2e_smoke.md` for current env behavior.
3. `AGENTS.md` sections on reduced scope guarantees.

## Implementation Scope & Deliverables
- Extend `ReducedScopeSettings` with a `use_real_tools` (or equivalent) toggle that flips `text_only_chunks`, `disable_valkey`, and `disable_rate_limiting` together when enabled.
- Update `Settings.load_settings()` to read new env vars: `REDUCED_SCOPE_USE_REAL_TOOLS`, `OPENAI_API_KEY`, `VOYAGE_API_KEY`, etc., and surface friendly errors when real mode is requested but secrets are absent.
- Modify `create_app()` to respect the new toggle (instantiate Valkey/rate limiter even in reduced profile when real mode is active).
- Add CLI/Compose knobs:
  - `REAL_REDUCED_E2E_TOOLS=1` for the wrapper (propagated into the container environment).
  - `--use-real-tools` Typer flag (with env mirror) so local runs can opt in without the wrapper.
- Update `.env.example`, `docs/testing/reduced_e2e_smoke.md`, `docs/runbooks/reduced_scope_demo.md`, and the repo “Golden Rules” to spell out the “no stubs in smoke/e2e” policy (call out the limited exceptions and unit-test patching guidance).

## Step-by-Step Instructions
1. Prototype the new settings flag and ensure reduced-mode defaults remain unchanged when the env var is unset.
2. Add validation logic during FastAPI startup (raise a descriptive error/log warning if real mode lacks required secrets).
3. Extend Compose wrapper + CLI configuration surfaces and add smoke tests verifying flag propagation.
4. Refresh docs/runbooks with a matrix comparing text-only vs real-tool modes.
5. Update `.env.example` comments for OpenAI/Voyage keys.
6. Run standard QA commands.

## Definition of Done
- A single flag (env/CLI) cleanly toggles between text-only and real-tool modes.
- Startup rejects misconfigured real-mode runs with actionable errors.
- Docs/runbooks clearly state which secrets are mandatory and how to toggle modes.
- QA suite passes.

## Handoff Notes
- Subsequent tasks wire the actual LangGraph runner + smoke CLI verification for real mode; record any follow-ups (e.g., metrics gaps, service restarts) discovered during this task.
- Call out any remaining assumptions about single-tenant secrets so later epics can expand credential management if needed.
