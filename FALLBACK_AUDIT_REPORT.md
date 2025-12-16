# Fallback/Dummy Logic Audit (Agent API, Ingestion Service, Shared Data Layer)

Scope: runtime code only for `services/agent-api`, `services/ingestion-service`, and `packages/shared_data_layer` (tests noted only when they indicate stubs used at runtime). Auth/user/etc. intentionally excluded.

## Agent API
- `src/agent_api/http/app.py`: `_initialize_cache_client` now fails unless `VALKEY_URL` is configured (in-memory is only allowed when `ALLOW_IN_MEMORY_VALKEY=1`); `_build_language_detector` swaps to `StubLanguageDetector` only when `ALLOW_STUB_LANGUAGE_DETECTOR=1`; rate limiter fails unless `ALLOW_RATE_LIMITER_BYPASS=1` is explicitly set.
- `src/cache/valkey_client.py`: in-memory Valkey stub is still available but only used when explicitly enabled (`ALLOW_IN_MEMORY_VALKEY=1`).
- `src/services/answer_composer.py`: returns reduced-scope fallback responses when OpenAI client absent or `use_real_tools` is false; also builds heuristic answers from chunks when the LLM returns an empty/short response, and injects default citations when none were retrieved.
- `src/services/numerical_fact_extractor.py`: falls back to regex parsing when the LLM is missing/fails and runs a “final fallback” regex sweep over combined text to avoid empty tables.
- `src/services/langgraph_runner.py`: `_numerical_fallback` disables `requires_sql` and downgrades to a guardrail warning when numerical tables aren’t built, instead of failing the request. (Earlier guardrail raises for missing OpenAI client.)
- `src/nodes/retrieval/graph_summarizer_node.py`: emits a generic fallback summary (headline only, `fallback_used=True`) when graph context is empty or trimmed to zero by budget.
- `src/nodes/retrieval/graph/repository.py`: `_fallback_entities` re-queries the base tables (ordered by `updated_at`) when hot-ranked entities are missing, hiding freshness/gap issues.
- `src/nodes/retrieval/workflow_planner_node.py`: defaults to the first workflow when none are prioritized, potentially masking misconfigured workflow selection.
- `src/subgraphs/informational/answer_synthesizer_node.py`: maintains a `fallback_cursor` to round-robin document entries when the reranker yields too few citations, ensuring some docs are surfaced even when relevance is low.
- `src/streaming/with_sse.py`: when guardrails imports fail, `RouterRoute` is replaced with `Any` (runtime fallback), meaning guardrail typing/coverage disappears silently.
- `src/services/reduced_scope_runtime.py`: synchronous demo/runtime creates placeholder artifacts and pillar answers in reduced scope, skipping real workers/export flows; logs and returns generated demo data.
- `src/services/ingestion_job_service.py`: `ReducedScopeIngestionJobService` auto-completes ingestion jobs and injects `reduced_scope` metadata stubs (`mode=text_only`, `auto_completed=True`) without real pipeline execution.
- `src/agent_api/cli.py`: CLI commands insert placeholder artifacts/ingestion completions via reduced-scope runtime helpers (no external storage/export).
- `src/streaming/with_sse.py` & `src/agent_api/http/app.py`: catch-all exception handlers convert unexpected errors to 500 payloads without surfacing root cause unless logs are inspected (not strictly a fallback, but hides specifics).

## Ingestion Service
- No runtime fallback/dummy code detected. Only a settings description references an auth-service “fallback” URL; the code path itself does not implement a fallback.

## Shared Data Layer
- Runtime: no fallback/dummy logic identified.
- Tests: `testing/factories/retrieval.py` uses `_document_stub()` for fixtures only (non-runtime).

## Notes/Next Steps
- Align with the “no fallbacks” policy by replacing the above branches with fail-fast behavior (raise/log/surface 4xx/5xx) or gate them behind explicit demo-only flags that default to hard failures in production configs.
- Prioritize removal of Valkey stubs and reduced-scope ingestion/answer fallbacks in production paths; ensure numerical/table flows fail when prerequisites (LLM/tables) are absent instead of silently degrading.
