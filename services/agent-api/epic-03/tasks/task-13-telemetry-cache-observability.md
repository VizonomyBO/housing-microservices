# Task 13 — Metrics, Cache Observability & Shared Data Layer Writers

## System Snapshot
- SSE emitters (Task 12) now exist and nodes fire events.
- CacheWriter, Router, HumanGate, and subgraphs expose telemetry hooks but do not yet record metrics or persist telemetry to shared tables.

## What You Inherit
- Shared data layer writers for `retrieval_runs`, `chunk_metrics`, `pillar_answers` are available (see `packages/shared_data_layer/telemetry`).
- Valkey client stub (Task 05) and CacheWriter (Task 07) already expose stats placeholders.

## Goal
Implement Prometheus/OTel metrics, cache observability helpers, and repository writers so retrieval/cache telemetry flows into the shared data layer.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.5 (metrics + cache observability deliverables).
2. `docs/overview/system_architecture.md` §3.7–3.8 (tracing, rate limiting, Valkey pooling requirements).
3. `docs/data/schema_and_persistence.md` §§3.7–3.8 (telemetry tables).
4. `docs/agents/implementation.md` SSE appendix (Task 12 update) for event names.

## Implementation Scope & Files
- `services/agent-api/src/telemetry/MetricsRegistry.ts`
- `services/agent-api/src/telemetry/CacheObservability.ts`
- Wiring inside nodes/subgraphs to emit metrics (latency, token usage, cache ratio, guardrail/HITL counts).
- Tests: `services/agent-api/tests/telemetry/`
- Documentation updates describing metrics + dashboards.

## Step-by-Step Instructions
1. **Metrics Registry**:
   - Initialize Prometheus counters/histograms (latency, token usage, cache_hit_ratio, hitl_pauses, guardrail_violations).
   - Provide OTel span helpers for propagation across async calls.
2. **Cache Observability Helper**:
   - Track Valkey pool stats, rate limiter checks, and integrate with CacheWriter to log hits/misses/writes.
   - Write telemetry to shared data layer tables (`retrieval_runs`, `chunk_metrics`, `pillar_answers`).
3. **Node Wiring**:
   - Update Router, subgraphs, HumanGate, CacheWriter to call metrics helper at key points.
   - Ensure SSE events (Task 12) include metric references when applicable.
4. **Integration Tests**:
   - Simulate LangGraph run covering cache hit, cache miss + write, and HITL pause/resume.
   - Verify metrics counters updated and telemetry records written.
5. **Docs & Dashboards**:
   - Document each metric (name, type, labels) and recommended Grafana dashboards.
   - Include instructions for configuring rate limiters + Valkey pooling.

## Definition of Done
- Metrics and cache observability modules implemented with test coverage.
- Telemetry writes proven via integration tests.
- Documentation references dashboards + operational playbooks.

## Handoff Notes
- Provide endpoints/paths for scraping metrics.
- Summarize how to replay telemetry in staging for validation.
