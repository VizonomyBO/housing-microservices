# Task 10 — Numerical Subgraph (Text-to-SQL + Validators)

## System Snapshot
- Informational & Analyst subgraphs exist (Task 09) along with CacheWriter/HumanGate infrastructure.
- Numerical-specific logic (text-to-SQL, Polars execution) is still missing.

## What You Inherit
- Router will route to Numerical subgraph when queries require computation.
- Shared data layer provides access to structured datasets referenced by retrieval context.
- Cache + HumanGate flows ready for reuse.

## Goal
Implement the Numerical subgraph including prompt builders, text-to-SQL node, Polars execution via `asyncio.to_thread`, validators, and artifact attachments (tables/charts).

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.4 (Numerical bullet).
2. `docs/agents/implementation.md` §4.3 (numerical reasoning flow).
3. `docs/interfaces/api_contracts.md` §3.4 (table/chart attachment schema in SSE stream).
4. `docs/overview/system_architecture.md` §3.6 (resource constraints, thread pools for heavy workloads).

## Implementation Scope & Files
- `services/agent-api/src/subgraphs/numerical/TextToSqlNode.ts`
- `services/agent-api/src/subgraphs/numerical/PolarsExecutorNode.ts`
- `services/agent-api/src/subgraphs/numerical/ResultValidatorNode.ts`
- Artifact helpers `services/agent-api/src/subgraphs/numerical/artifacts.ts`
- Tests `services/agent-api/tests/subgraphs/numerical/`
- Update acceptance doc (`services/agent-api/epic-03/subgraph-acceptance.md`) with Numerical section.

## Step-by-Step Instructions
1. **Prompt Builder**: deterministic template referencing retrieval context + workflow plan; ensure parameters documented.
2. **TextToSQL Node**:
   - Use LLM/tooling to propose SQL; validate schema names using shared data layer metadata.
   - Provide guardrail for unsupported joins/queries.
3. **PolarsExecutor Node**:
   - Run generated SQL via Polars inside `asyncio.to_thread` (or Node equivalent using worker threads) to keep event loop free.
   - Capture execution metrics (duration, row count) for telemetry.
4. **ResultValidator**:
   - Enforce schema + bounds checks; on failure escalate via HumanGate.
5. **Artifacts**:
   - Generate table preview + chart spec attachments for SSE streaming.
6. **Testing**:
   - Mock dataset to validate SQL generation + execution.
   - Failure paths (invalid SQL → guardrail; validator catches out-of-bounds values → HumanGate).
7. **Docs**:
   - Document prompt template, execution strategy, and how artifacts are serialized.

## Definition of Done
- Numerical nodes implemented with full test coverage.
- Threaded execution prevents event loop blocking.
- Acceptance doc updated with Numerical validation steps.

## Handoff Notes
- Provide instructions for configuring test datasets.
- List telemetry metrics to hook later (Task 13).
