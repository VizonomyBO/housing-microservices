# Tracker: Remove fallbacks / enforce real deps
_(Keep in sync with `TASK_PLAN_NO_FALLBACKS.md`.)_

- [x] Review current fallback/stub code paths and env flag defaults.
- [x] Restore fail-fast behavior across ingestion/retrieval/langgraph/answer composer/eval harness; remove placeholder entities/chunks/zero-vector fallbacks.
- [ ] Ensure tests/evals use real keys (non-unit) and adjust settings/env wiring per requirements; keep ALLOW_* flags accessible.
- [ ] Run required quality gates for agent-api (`ruff format`, `ruff check --fix`, `ty check`, `pytest -n auto`) and note results.
- [ ] Summarize changes, test outcomes, and any remaining risks.
