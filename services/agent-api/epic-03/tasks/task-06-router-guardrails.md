# Task 06 — Router Classification & Guardrail Policies

## System Snapshot
- Retrieval stack (Tasks 03–05) produces normalized prompts, attachment scopes, graph summaries, and workflow plans with cache metadata.
- No routing or guardrail enforcement is in place yet; Router will consume retrieval context to choose subgraphs.

## What You Inherit
- `AgentState` persistence & checkpoints (Tasks 01–02).
- Cache key helper + WorkflowPlanner outputs (Task 05).
- SSE + telemetry hooks are not yet implemented (they arrive in Tasks 12–13); add TODOs where events will fire.

## Goal
Implement the Router node and guardrail policy framework that classifies requests into `{Informational, Analyst, Numerical, Vision, Escalate}` and validates attachments/compliance before subgraphs execute.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.3 (routing + guardrail expectations).
2. `docs/agents/implementation.md` §4 (routing flow, escalation logic).
3. `docs/security/guardrails.md` and `docs/security/prompt_policy.md` (if applicable) — define compliance filters.
4. `docs/interfaces/api_contracts.md` §3 (SSE/telemetry fields for routing decisions).

## Implementation Scope & Files
- `services/agent-api/src/nodes/router/router_node.py`
- Guardrail framework under `services/agent-api/src/guardrails/` (policy definitions, validators, error codes).
- Tests under `services/agent-api/tests/router/` and `tests/guardrails/`.
- Documentation updates describing classification + guardrail policies.

## Step-by-Step Instructions
1. **Policy Definitions**:
   - Create declarative policy config (JSON/YAML or TS object) describing prompt rules, attachment constraints, compliance filters.
   - Provide validator utilities that accept normalized input + attachment metadata (from Task 03) and return `GuardrailResult` objects.
2. **Router Node**:
   - Accept retrieval context + WorkflowPlanner output.
   - Run guardrails first; on failure emit `route = Escalate` with violation codes.
   - Otherwise classify using heuristics + optional LLM scoring (deterministic prompts). Keep the classification reproducible.
3. **Outputs**:
   - Return `route`, `confidenceScore`, `guardrailFindings`, `nextSubgraph` pointer, and `cache_metadata` (pass through from Task 05).
4. **Testing**:
   - Guardrail tests covering allowed/blocked attachments, prompt policy violations, compliance filters.
   - Router tests for each route type; ensure guardrail failures force `Escalate`.
5. **Docs**:
   - Document policy files, guardrail codes, and Router decision tree.

## Definition of Done
- Guardrail framework + Router node implemented with exhaustive unit tests.
- Outputs include structured violation data for HumanGate.
- Docs describe how to adjust policies and how Router interacts with downstream subgraphs.

## Handoff Notes
- Provide location of policy config and instructions for adding new policies.
- Share sample Router output for Task 07 (CacheWriter) and Task 08 (HumanGate).
