# Task 01 — AgentState Schema Foundation

## System Snapshot
- Repository is a monorepo; LangGraph agent service will live under `services/agent-api` (new in Epic 3).
- Prior epics delivered the shared data layer (`packages/shared_data_layer`) and database schema (see `docs/data/schema_and_persistence.md` §§3.6–3.8) plus the overall LangGraph design (`docs/agents/implementation.md` §§3–5).
- You are starting fresh each session: re-read the docs referenced below to rebuild context before writing code.

## What You Inherit
- No code exists yet in `services/agent-api/src/`; you will create the foundational state module.
- Epic 1 already provisioned tables: `conversations`, `messages`, `conversation_documents`, `agent_state_checkpoints`.
- Subsequent tasks will rely on the `AgentState` typing decisions you make here.

## Goal
Define a strongly typed `AgentState` domain model that mirrors LangGraph checkpoints, documents serialization requirements, and prepares factories/utilities future tasks will reuse.

## Must Read Before Coding
1. `docs/overview/system_architecture.md` §3 — explains runtime topology and how the agent orchestrator persists state.
2. `docs/agents/implementation.md` §§3–5 — describes LangGraph nodes, state expectations, and HITL pause/resume flow.
3. `docs/data/schema_and_persistence.md` §§3.6–3.8 — details the schema for conversations, checkpoints, and telemetry tables.
4. `docs/epics/03.md` (Task 3.1 section) — high-level expectations for this state work.

## Implementation Scope & Files
- Create `services/agent-api/src/state/agent_state.py`.
- If shared types are needed for other packages, expose them via `services/agent-api/src/state/__init__.py`.
- Add accompanying unit tests under `services/agent-api/tests/state/test_agent_state.py`.
- Documentation snippet to be appended later (Task 02) — note TODO markers where context is needed.

## Step-by-Step Instructions
1. **Model Fields**: Include `messages`, `graph_context`, `workflow_plan`, `cache_metadata`, `retrieval_metrics`, `vision_findings`, `interrupt_reason`, `checkpoint_id`, `conversation_id`, and `created_at`. Document each property with comments referencing the doc sections above.
2. **Type Safety**: Model the structure with Pydantic v2 (`BaseModel` subclasses) so runtime validation is automatic. Provide helper data classes for `MessageSnapshot`, `GraphContext`, etc., and use LangChain `BaseMessage` objects (or adapter helpers) for the `messages` collection to keep parity with LangGraph.
3. **Serialization Helpers**: Implement `to_persistence(state)` and `from_persistence(row_set)` so repository code can convert between in-memory and DB representations (JSON columns vs. relational tables).
4. **Validation**: Let Pydantic handle runtime validation (custom validators where needed) ensuring required fields exist before serialization. Keep validation light-weight to avoid runtime cost.
5. **DB Contract Clarity**: Document the JSON payload stored in `agent_state_checkpoints.state`, including a `cache_metadata.schema_version` (default `1`) so migrations stay cheap. Call out any shared-data-layer follow-ups (e.g., TODOs for Task 02 when repository writers wire in the shared package) if schema changes are required.
5. **Testing**: Cover
   - Schema instantiation with minimum required fields.
   - Validation failures for missing mandatory properties.
   - Round-trip serialization (object -> persistence payload -> object).

## Definition of Done
- `AgentState` type exported with docstrings.
- Helper functions exist for serialization/deserialization + validation.
- Tests pass locally (document the command you ran, e.g., `pnpm test agent-state`).
- File headers or comments cite relevant doc sections for future readers.

## Handoff Notes
- Include the exact file paths created.
- Mention any TODOs left for Task 02 (repository integration).
- Provide test command/output snippet for reviewers.
