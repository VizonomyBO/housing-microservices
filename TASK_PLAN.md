### Task Plan (auto-approved; proceeding now)

**Request:** Investigate why the agent conversation endpoint (conversation id `6a31013a-b991-5237-8ba3-c3ff38a908df`) failed to recall the prior message, and identify design flaws in the memory/response logic. Avoid code changes until root cause is understood.

**Scope / Likely Areas:** Agent conversation retrieval + summarization logic (conversation endpoint), dialogue memory storage (DB/cache), auth/config tied to `.env.prod`, any middleware that truncates context.

**Risks/Constraints:** Prod data access must be read-only; avoid destructive commands. Possible confusion between ingestion-task artifacts vs. agent conversation flow. Need to respect AGENTS instructions and avoid accidental dependency/drift changes.

**Ordered Steps:**
1. [x] Review existing docs/AGENTS guidance relevant to agent conversation handling and any conversation endpoint specs.
2. [x] Inspect code paths for conversation retrieval/history (API handler, services, memory layers) to see how context is fetched and passed to the LLM.
3. [x] Look for logging/telemetry or persistence schema that could explain missing turn (e.g., pagination limits, summarization gaps, role filters).
4. [x] Reconstruct expected conversation flow for id `6a31013a-b991-5237-8ba3-c3ff38a908df` and hypothesize failure modes (e.g., lack of stateful session, incorrect conversation_id handling).
5. [x] Propose fixes or next checks (and any verification steps) without making prod-impacting changes.
6. [x] Update docs and AGENTS.md to reflect conversation memory requirements and usage.
7. [x] Enforce UUID/ownership validation on `/v1/chat`, making stateless fallback opt-in and returning 4xx for unknown/foreign conversations.
8. [x] Add pagination/cursor limits to GET `/v1/conversations/{id}` transcript payload to prevent oversized responses.
9. [x] Introduce a caching layer for transcript summaries (e.g., last message, counts) to speed listing/summary endpoints.
10. [x] Add observability: metric on history load and warning when stateless fallback occurs; log route/conversation_id in checkpoint writes.
11. [x] Extend CLI/e2e/regression coverage: multi-turn continuity with attachments and ownership rejection for foreign conversations.
12. [x] Run quality gates (ruff format/check, ty, pytest) and summarize results.

**Research Sources (update as we learn):**
- AGENTS.md (repo root) for process rules.
- services/agent-api/AGENTS.md (service-specific workflow).
- docs/interfaces/api_contracts.md (§1.3–1.4 `/v1/chat` and conversation retrieval contract).
- services/agent-api/epic-reduced-e2e/tasks/task-06-conversation-endpoint.md (conversation lifecycle endpoints scope).
