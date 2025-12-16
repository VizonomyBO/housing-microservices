# Plan: Remove newly added fallbacks and enforce real dependencies
_(Auto-approved per AGENTS.md; proceeding immediately. Tracker: `TASK_PLAN_NO_FALLBACKS_PROGRESS.md`.)_

## Request
- Remove the recently introduced fallbacks/stubs (retrieval, embeddings, graph entities, numerical, answer composer, eval runner) so the Agent API fails fast instead of synthesizing placeholder outputs.
- Ensure non-unit tests/evals use real OpenAI/Guardrails/Valkey (no stubs); keep ALLOW_* flags available but rely on real services.
- Rerun agent-api tests and report results; keep prod behavior aligned with no-fallback expectations.

## Impacted files (expected)
- services/agent-api/src/services/{ingestion_pipeline.py,langgraph_runner.py,answer_composer.py}
- services/agent-api/src/nodes/retrieval/{attachment_scope_loader_node.py,graph/repository.py}
- services/agent-api/tests/**/* (eval runner, smoke harness, numerical tests)
- services/agent-api/src/agent_api/settings.py and related deps/env wiring

## Risks / Checks
- Removing fallbacks may reintroduce test failures if real deps aren’t reachable; need env vars for OpenAI/Valkey/rate limiter/lingua set correctly.
- Prod must not silently degrade; ensure no hidden stub paths remain.
- Test runtime may increase due to real OpenAI calls; watch for rate limits.

## Research notes
- References: AGENTS.md (fail-fast rules, uv-first), memory bank tasks.md (fail-fast deps), README.md for startup expectations.

## Steps
- [ ] Review current fallback/stub code paths and env flag defaults.
- [ ] Restore fail-fast behavior across ingestion/retrieval/langgraph/answer composer/eval harness; remove placeholder entities/chunks/zero-vector fallbacks.
- [ ] Ensure tests/evals use real keys (non-unit) and adjust settings/env wiring per requirements; keep ALLOW_* flags accessible.
- [ ] Run required quality gates for agent-api (`ruff format`, `ruff check --fix`, `ty check`, `pytest -n auto`) and note results.
- [ ] Summarize changes, test outcomes, and any remaining risks.
