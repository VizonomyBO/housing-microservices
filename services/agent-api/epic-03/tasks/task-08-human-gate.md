# Task 08 — HumanGate Pause/Resume Node

## System Snapshot
- Router (Task 06) emits guardrail findings + confidence scores.
- CacheWriter (Task 07) provides serialization + cache helpers.
- Checkpoint persistence (Tasks 01–02) supports saving/resuming runs.

## What You Inherit
- Structured `AgentState` updates, guardrail violation codes, and cache metadata.
- SSE/metrics layer not yet implemented; add TODO hooks for Task 12–13.

## Goal
Implement the HumanGate node that evaluates confidence + policy outputs, pauses LangGraph runs for HITL review, and resumes them using checkpoint services.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.3 (HumanGate requirements).
2. `docs/agents/implementation.md` §5 (HITL pathways, resume tokens, SSE events).
3. `docs/interfaces/api_contracts.md` §3.2 (HITL pause/resume streaming events).
4. `docs/overview/system_architecture.md` §3.5 (HITL services integration).

## Implementation Scope & Files
- `services/agent-api/src/nodes/human/HumanGateNode.ts`
- Helper `services/agent-api/src/hitl/HumanGateService.ts`
- Tests `services/agent-api/tests/nodes/human/HumanGateNode.test.ts`
- Documentation updates on HITL pause/resume lifecycle.

## Step-by-Step Instructions
1. **Confidence Evaluation**:
   - Define thresholds for each route type (config-driven). If confidence below threshold or guardrail violation exists, trigger HITL.
2. **Pause Flow**:
   - Serialize current `AgentState` using Task 01 helpers.
   - Save checkpoint via repository (Task 02) with `interrupt_reason` and `resume_token`.
   - Emit placeholder SSE events (`hitl_pause`) with payload (wired later).
3. **Resume Flow**:
   - Provide entry point `resumeFromHitl(resumeToken)` that loads checkpoint, updates state, and returns control to LangGraph.
   - Ensure resumed runs append HITL transcript metadata.
4. **Testing**:
   - Force low-confidence scenario: expect checkpoint persisted + pause result.
   - Resume scenario: simulate HITL approval -> ensure state restored and run continues.
5. **Docs**:
   - Document state transitions, SSE payload expectations, and how HITL operators interact (link to `docs/interfaces/api_contracts.md`).

## Definition of Done
- HumanGate node + service implemented with thresholds configurable.
- Pause/resume logic fully tested.
- Docs updated with HITL flow referencing repository APIs.

## Handoff Notes
- Provide instructions for hooking SSE + metrics later.
- Share threshold config file paths for future tuning.
