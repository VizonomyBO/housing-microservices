# Subgraph Acceptance Criteria (Epic 3)

Use this file to record QA criteria per modality as tasks are completed.

## Informational Subgraph (Task 09)
- AnswerSynthesizer short-circuits on Valkey hits via `maybe_serve_from_cache` and emits deterministic answer/citation payloads with cache metadata preserved.
- CitationVerifier validates every citation against retrieved context, records `citation_mismatch` guardrail violations, and routes to HumanGate with `interrupt_reason=invalid_citation` when evidence is missing.
- Cache misses drive the composer path (LLM adapter) and populate `answer_chunk_ids`, `answer_metadata`, and `quality_score` for downstream streaming/CacheWriter usage.
- Integration test `tests/subgraphs/test_informational_flow.py` exercises the happy path (cache miss → synthesis → verification) while unit tests cover cache hits and invalid citation HITL escalation.
- SSE emitters instrument these nodes (Task 12) to produce cache hit/miss/write frames plus `agent_cache_events_total` metric references; wiring the FastAPI SSE endpoint will surface these events to clients without further node changes.

## Analyst Subgraph (Task 09)
- AnalystPlanner translates `workflow_plan` outputs into `AnalystPlan` (step metadata + complexity telemetry), updating `subgraph_metrics` for eventual SSE streaming.
- ComparisonSynthesizer builds the final analyst answer plus attachments, persists Valkey entries through `CacheWriter`, and captures highlights for streaming clients.
- Tests (`tests/subgraphs/analyst/*`) verify plan generation, cache writes, attachment serialization, and builder integration.
- HumanGate escalation for analyst mode piggybacks on CitationVerifier logic via guardrails; additional analyst-specific guardrails/telemetry land in Tasks 10–13.
- Task 12 instrumentation now emits analyst-specific SSE metrics (`analyst.plan.*`, `analyst.comparison.*`) with cache/HITL metric references ready for consumption once the HTTP streaming endpoint is wired.

## Numerical Subgraph (Task 10)
- TextToSQL node (`subgraphs/numerical/text_to_sql_node.py`) builds deterministic prompts from workflow plans + table schemas, validates generated SQL against shared metadata, and records guardrail violations (code `numerical_sql`) before routing to HumanGate on unsupported joins.
- Polars executor node (`subgraphs/numerical/polars_executor_node.py`) registers only the selected table with `pl.SQLContext`, executes queries inside `asyncio.to_thread`, and records execution metrics (`numerical.polars.*`) alongside materialized rows.
- Result validator (`subgraphs/numerical/result_validator_node.py`) enforces schema + column bounds, emits `numerical_validation` guardrails, and optionally pauses via HumanGate when numeric ranges are violated or result sets are empty.
- Artifact helpers (`subgraphs/numerical/artifacts.py`) serialize table previews and heuristic chart specs that align with the SSE attachment contract (table/chart payloads) so Guardrails/Router can stream them downstream.
- Tests in `tests/subgraphs/numerical/` cover SQL prompt guardrails, Polars execution success/error cases, and validator → HumanGate escalation, ensuring failure paths (invalid SQL, out-of-bounds rows) are deterministic.

## Vision Subgraph (Task 11)
- VisionRouterNode inspects attachment metadata, computes `vision_context.mode` (image-only vs multimodal), logs warnings for missing captions, and enforces guardrail codes `vision_mime_type` + `vision_policy` before proceeding.
- ImageReasonerNode consumes `image_caption` chunks (falling back to deterministic descriptors as needed), records warnings in `error_log`, and populates `vision_findings` with model metadata/figures referenced for downstream nodes + Guardrails.
- MultimodalResponderNode merges visual findings with textual prompts, writes deterministic cache payloads (`CacheWriter`), annotates `answer_metadata["vision_attachments"]`, and routes to HumanGate when any blocking vision guardrails remain.
- Tests under `tests/subgraphs/vision/test_vision_nodes.py` cover image-only vs multimodal flows, cache writes, and guardrail-triggered HITL routing.
- Task 12’s SSE hooks emit `vision.router.mode`, `vision.reasoner.findings`, `vision.responder.attachments`, and the `vision_attachments` list from `answer_metadata`; wiring the streaming endpoint will expose these frames without additional node work.
