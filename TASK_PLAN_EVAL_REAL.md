# Task Plan – Restore real eval/smoke dependencies (auto-approved)

## Summary
- Objective: remove eval/smoke stubs and run with real dependencies (OpenAI, guardrails, prod data) using `.env.prod` secrets; avoid Graph/Valkey/rate-limit 503s while preserving fail-fast prod behavior.
- Root `TASK_PLAN.md` / `TASK_PLAN_PROGRESS.md` remain untouched; this file is ephemeral.

## Impacted Areas
- `services/agent-api/tests/evals/*`, `tests/scripts/test_run_reduced_e2e_smoke.py` (remove stubs).
- Env/test harness for evals to load `.env.prod` values and point at real stack.

## Risks / Watchouts
- Using prod DB/stack can mutate data; ensure calls are safe/expected.
- OpenAI calls incur cost and need valid key from `.env.prod`.
- Removing stubs may slow tests; ensure flags allow Valkey/rate-limiter bypass only in test contexts.

## Research / Sources
- `.env.prod` for real secrets/endpoints.
- Guardrails package already imported from local module; OpenAI API per OpenAI client.

## Plan
- [ ] Capture current stub usage and failure points; outline removals.
- [ ] Remove eval/smoke stubs; wire eval tests to real runner/metric engine.
- [ ] Load `.env.prod` in eval tests and force remote stack usage (AGENT_BASE_URL/auth secret/openai).
- [ ] Ensure Graph/Valkey/rate-limit dependencies satisfied without reintroducing fallbacks.
- [ ] Run quality gates as feasible (ruff format/check, ty, pytest) and verify.
- [ ] Clean up this plan/tracker when done.
