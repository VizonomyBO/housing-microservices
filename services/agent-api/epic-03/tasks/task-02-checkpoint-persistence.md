# Task 02 — Checkpoint Persistence & HITL Metadata

## System Snapshot
- Task 01 established `AgentState` types and serialization helpers in `services/agent-api/src/state/`.
- Shared data layer (`packages/shared_data_layer`) already exposes repositories for `conversations`, `messages`, `conversation_documents`, and `agent_state_checkpoints`.
- Human-in-the-loop (HITL) checkpoints and SSE communication are described in `docs/agents/implementation.md` §5.

## What You Inherit
- Use the `AgentState` module created in Task 01 (verify types + helpers before coding).
- Database schemas are defined; do not alter migrations.

## Goal
Implement repository adapters and integration tests ensuring LangGraph nodes can save/load checkpoints, including HITL pause metadata, via the shared data layer.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.1 subsections (state + checkpoints).
2. `docs/agents/implementation.md` §§4–5 (LangGraph state machine, HITL flows, resume tokens).
3. `docs/data/schema_and_persistence.md` §§3.6–3.7 (table contracts for `agent_state_checkpoints` and message hydration).
4. `docs/interfaces/api_contracts.md` §3.2 (streaming + interrupt events that rely on checkpoints).

## Implementation Scope & Files
- Create `services/agent-api/src/repositories/AgentCheckpointRepository.ts`.
- Add high-level service wrapper `services/agent-api/src/services/CheckpointService.ts` if orchestration logic (HITL vs. normal) is needed.
- Tests: `services/agent-api/tests/repositories/AgentCheckpointRepository.test.ts` (integration style; use sqlite or shared mocks).
- Update docs: add a subsection to `docs/agents/implementation.md` referencing the repository API and HITL metadata handling.

## Step-by-Step Instructions
1. **Repository Adapter**:
   - Provide `saveCheckpoint(state: AgentState, options)` storing JSON payloads + metadata columns.
   - Provide `loadLatest(conversationId)` and `loadByCheckpointId(conversationId, checkpointId)`.
   - Enforce visibility by joining `conversation_documents` and filtering hidden documents.
2. **Hydration Logic**:
   - Compose messages from `messages` table sorted chronologically.
   - Attach document metadata with respect to `visibility_override` flags.
3. **HITL Metadata**:
   - Persist `interrupt_reason`, `resume_token`, `hitl_operator_id` as part of checkpoint payload.
   - Provide helper `resumeFromHitl(conversationId, resumeToken)` that fetches the paused checkpoint and returns the stored `AgentState`.
4. **Testing**:
   - Scenario 1: Save checkpoint, then load latest — expect structural equality with the original `AgentState`.
   - Scenario 2: Save HITL pause checkpoint, ensure `resumeFromHitl` returns metadata and clears/updates status as designed.
   - Scenario 3: Visibility enforcement (hidden document should not appear after hydration).
5. **Docs**:
   - Document repository APIs, expected parameters, and how HITL tooling interacts with them.
   - Link back to Epic 1 tables to show continuity.

## Definition of Done
- Repository/service classes exist with full TypeScript types and JSDoc.
- Tests cover normal + HITL flows and visibility constraints.
- Docs updated with checkpoint lifecycle narrative.
- Lint/tests pass locally (record command/output).

## Handoff Notes
- Summarize repository API signatures and entry points for LangGraph nodes (later tasks rely on this).
- Mention how to configure DB/test harness for subsequent agents.
