### Task Plan – Conversation Memory Investigation (auto-approved)

**Request:** Diagnose why the conversation endpoint (id `6a31013a-b991-5237-8ba3-c3ff38a908df`) responded as if it lacked prior message context, and identify any design flaws in agent memory/response handling.

**Scope / Impacted Areas:** FastAPI conversation endpoint(s), LangGraph/chat orchestration, memory storage/retrieval (DB/cache), any summarization or truncation layers, production configuration (.env.prod) used by the agent when answering via the conversation endpoint.

**Risks/Constraints:** Read-only when inspecting prod data; avoid destructive commands. Keep changes scoped to `services/agent-api` unless memory storage lives elsewhere. Ensure findings align with AGENTS guidelines and avoid altering ingestion tasks.

**Ordered Steps:**
1. [x] Review agent conversation docs/specs and relevant epic/task files for chat/memory flows.
2. [x] Trace the code path for fetching conversation history and constructing LLM prompts; note pagination/limits and role filtering.
3. [x] Inspect persistence/logging/telemetry to see if prior turns are stored/fetched correctly (e.g., DB queries, summarization checkpoints).
4. [x] Analyze the provided conversation example to map expected vs. actual messages and identify potential failure modes (missing state, bad conversation_id, summarization overwrite).
5. [x] Recommend fixes or next verifications (tests/observability), keeping runtime safety in mind.
6. [x] Update docs and AGENTS guidance to reflect conversation memory expectations/usage.
7. [x] Enforce UUID/ownership validation on `/v1/chat`, making stateless fallback opt-in with 4xx on unknown/foreign conversations.
8. [x] Add transcript pagination/cursors to GET `/v1/conversations/{id}` to keep responses bounded.
9. [x] Add caching for transcript summaries (last message, counts) to accelerate listing/summary endpoints.
10. [x] Add observability: `history_loaded` metric, fallback warning, and logging route/conversation_id in checkpoints.
11. [x] Extend CLI/e2e/regression coverage (multi-turn continuity, attachment reuse, ownership rejection).
12. [x] Run quality gates (ruff format/check, ty, pytest) and summarize results.

**Research Sources (update as we learn):**
- services/agent-api/AGENTS.md (process).
- docs/interfaces/api_contracts.md (§1.3 `/v1/chat`, §1.4 conversation retrieval contract).
- services/agent-api/epic-reduced-e2e/tasks/task-06-conversation-endpoint.md (conversation lifecycle HTTP design).
