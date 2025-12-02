# Subgraph Acceptance Criteria (Epic 3)

Use this file to record QA criteria per modality as tasks are completed.

## Informational Subgraph (Task 09)
- AnswerSynthesizer short-circuits on Valkey hits via `maybe_serve_from_cache` and emits deterministic answer/citation payloads with cache metadata preserved.
- CitationVerifier validates every citation against retrieved context, records `citation_mismatch` guardrail violations, and routes to HumanGate with `interrupt_reason=invalid_citation` when evidence is missing.
- Cache misses drive the composer path (LLM adapter) and populate `answer_chunk_ids`, `answer_metadata`, and `quality_score` for downstream streaming/CacheWriter usage.
- Integration test `tests/subgraphs/test_informational_flow.py` exercises the happy path (cache miss → synthesis → verification) while unit tests cover cache hits and invalid citation HITL escalation.
- Outstanding TODO (Task 12): wire SSE metrics for cache events + HITL payloads emitted by these nodes; placeholders live in `subgraph_metrics`.

## Analyst Subgraph (Task 09)
- AnalystPlanner translates `workflow_plan` outputs into `AnalystPlan` (step metadata + complexity telemetry), updating `subgraph_metrics` for eventual SSE streaming.
- ComparisonSynthesizer builds the final analyst answer plus attachments, persists Valkey entries through `CacheWriter`, and captures highlights for streaming clients.
- Tests (`tests/subgraphs/analyst/*`) verify plan generation, cache writes, attachment serialization, and builder integration.
- HumanGate escalation for analyst mode piggybacks on CitationVerifier logic via guardrails; additional analyst-specific guardrails/telemetry land in Tasks 10–13.
- SSE placeholders remain in `subgraph_metrics` pending Task 12 event emitters.

## Numerical Subgraph (Task 10)
- TODO: populate once Task 10 implements nodes.

## Vision Subgraph (Task 11)
- TODO: populate once Task 11 implements nodes.
