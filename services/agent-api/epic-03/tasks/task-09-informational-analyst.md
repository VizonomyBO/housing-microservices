# Task 09 — Informational & Analyst Subgraphs

## System Snapshot
- Upstream pipeline (Tasks 01–08) provides: normalized inputs, retrieval context, workflow plans, router decisions, guardrail results, cache helpers, and HumanGate pause/resume.
- No modality subgraphs exist yet. You will implement the Informational + Analyst flows first.

## What You Inherit
- CacheWriter API (Task 07) for storing final answers.
- Router indicates when Informational vs. Analyst subgraphs should run.
- Graph context + workflow plans ready to consume.

## Goal
Create Informational and Analyst LangGraph subgraphs with nodes (`AnswerSynthesizer`, `CitationVerifier`, `AnalystPlanner`, `ComparisonSynthesizer`) plus telemetry hooks placeholders.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.4 (subgraph requirements).
2. `docs/agents/implementation.md` §4.1 (Informational) & §4.2 (Analyst) for expected flows.
3. `docs/interfaces/api_contracts.md` §3 (streaming format for citations + analyst comparisons).
4. `docs/overview/system_architecture.md` §3.6 (telemetry expectations for subgraphs).

## Implementation Scope & Files
- `services/agent-api/src/subgraphs/informational/answer_synthesizer_node.py`
- `services/agent-api/src/subgraphs/informational/citation_verifier_node.py`
- `services/agent-api/src/subgraphs/analyst/analyst_planner_node.py`
- `services/agent-api/src/subgraphs/analyst/comparison_synthesizer_node.py`
- Shared utilities (prompt builders, telemetry helper stubs) as needed.
- Tests per subgraph under `services/agent-api/tests/subgraphs/`.
- Acceptance criteria doc `services/agent-api/epic-03/subgraph-acceptance.md` (create + start populating for Informational + Analyst sections).

## Step-by-Step Instructions
1. **AnswerSynthesizer**:
   - Combine retrieval context + workflow plan to draft initial answer.
   - Support cache lookup via CacheWriter helper (serve cached answer if available).
2. **CitationVerifier**:
   - Validate citations reference retrieved chunks; mark invalid references for HITL fallback (use HumanGate when necessary).
3. **AnalystPlanner**:
   - Build structured plan for analytical tasks (comparisons, calculations) referencing workflow steps.
   - Emit telemetry placeholder for plan complexity.
4. **ComparisonSynthesizer**:
   - Generate final analyst response referencing plan + retrieval data.
   - Serialize attachments for downstream streaming.
5. **Fallbacks**:
   - On guardrail violation or invalid citation, call HumanGate (Task 08) and stop further processing.
6. **Testing**:
   - Unit tests for each node (happy path + cache hit + invalid citation forcing HITL).
   - Integration test covering Informational path end-to-end (Normalization → Router stub → Answer synth/verifier).
7. **Acceptance Criteria Doc**:
   - Document verification steps, cache integration, SSE placeholders (will be filled Task 12), and QA checks.

## Definition of Done
- Informational & Analyst nodes implemented with tests.
- Cache + HumanGate integrations verified.
- Acceptance criteria doc updated for these subgraphs.

## Handoff Notes
- Provide links to acceptance doc sections.
- List outstanding TODOs for telemetry (Task 12–13) to avoid duplication.
