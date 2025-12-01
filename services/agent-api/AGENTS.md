# Agent Guide – Agent API Service

This is the canonical playbook for all agents working inside `services/agent-api`. Follow it exactly so every fresh session can deliver predictable, production-grade results.

- ✅ **Service status**: New LangGraph microservice implementing Epic 3 (see `services/agent-api/epic-03/tasks`). Nothing is deployed yet, but the shared schemas in `packages/shared_data_layer` are stable. Treat every change as production-ready.
- 🐍 **Runtime**: Python 3.13 managed by `uv` (virtual env lives at `services/agent-api/.venv`).
- 📚 **Source of truth**: Epic 3 task files under `services/agent-api/epic-03/tasks`. Complete them sequentially and update the checklist after each task.
- 🧱 **Language & frameworks**: All service code is Python. Use Pydantic models (v2) for runtime validation/serialization and LangChain `BaseMessage` objects (or adapters) for conversational payloads and HITL checkpoints.
- 🚫 **Avoid automation helpers**: Ignore `run_tasks.sh` and `RUN_TASKS.md`. Those files exist for humans orchestrating Codex sessions and must not influence how you plan or code a task.

## 1. Always Plan → Research → Act → Verify

### Plan
1. **Create a task-specific plan file** before touching code: `services/agent-api/TASK_<id>_PLAN.md`. Summarize the request, impacted files, risks, and ordered steps referencing the relevant epic task doc. Plans are auto-approved—note that in the file and proceed immediately, then treat the plan as ephemeral (delete it when the task is done).

### Research (prioritize external validation)
- For every open question, **start with web research and Context7 documentation**. Capture the sources (URLs or doc IDs) inside the plan so reviewers see what informed the decisions.
- When using libraries/APIs, read their docs via Context7 or web search before coding. Avoid hallucinations by quoting the reference in commit notes or doc comments when helpful.

### Act
1. **Create a tracker file** for the plan: `services/agent-api/TASK_<id>_TRACKER.md` (no waiting period; every plan is implicitly approved).
2. Mark the ordered steps `[ ]` → `[x]` as you complete each chunk of work. Keep the tracker up to date throughout the task.
3. Scope edits to this service unless a task explicitly says to touch shared packages. If you must modify the DB layer, conform to `packages/shared_data_layer/AGENTS.md` rules and reuse its factories/repositories.
4. Prefer incremental commits grouped by subsystem (state, repositories, nodes, docs, etc.).

### Verify
1. **Run the standard command suite** (see §3) every time you reach a review-ready state.
2. When DB interactions exist, rely on the shared data layer test harness and Testcontainers; never spin up Docker manually.
3. After successful verification, remove both the tracker file and the plan file, then document the commands/output in your final response along with links to affected files.
4. Update `services/agent-api/epic-03/CHECKLIST.md` to reflect the newly completed task (mark checkbox, add notes, or reorganize downstream tasks if scope changed).

---

## 2. Task Intake & Documentation Expectations

1. **Read the relevant epic doc** (`docs/epics/03.md`) plus the referenced design sections before planning.
2. Each task file in `services/agent-api/epic-03/tasks` contains prerequisites (“System Snapshot”, “What You Inherit”, etc.). Assume the agent starts from zero context—re-read those sections every session.
3. Keep documentation synchronized:
   - Update `docs/agents/implementation.md`, `docs/overview/system_architecture.md`, or other references when tasks require doc changes.
   - If you finish a task that alters subsequent work, edit the associated task files or checklist entries to prevent drift.
   - If a prerequisite is missing, author/adjust additional task files and reorder the checklist so future agents inherit a coherent plan.

---

## 3. Environment, Commands & Tools (uv-first)

Operate from `services/agent-api` and rely on `uv` for everything: Python installation, dependency sync, scripts, and tool execution.

| Purpose | Command | Notes |
| --- | --- | --- |
| Ensure env exists | `uv venv --python 3.13 .venv` | Already created; rerun if `.venv` missing. |
| Install/update deps | `uv sync --all-extras` | Reads `pyproject.toml` / `uv.lock`; adds/updates `.venv`. |
| Add a dependency | `uv add <package>` | Automatically resolves + updates lock. Prefer `uv add --dev` for dev tools. |
| Pin Python version | `uv python pin 3.13` | Writes `.python-version` for reproducible local runs. |
| Lock dependencies | `uv lock` | Re-resolve + refresh `uv.lock`. |
| Run scripts/commands | `uv run <command>` | Ensures the `.venv` + pinned Python are used. |
| Pip-compatible sync | `uv pip sync requirements.txt` | Use when tasks require legacy `requirements` files. |
| Install CLI tool | `uv tool install <pkg>` / `uvx <tool>` | e.g., `uv tool install ruff`. |

**Standard quality gates (same as shared data layer)**
Run these (via `uv run`) before marking a task complete:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```

- Targeted tests are encouraged during development (e.g., `uv run pytest tests/nodes/retrieval/test_graph.py`).
- When DB coverage is required, rely on the in-repo Testcontainers fixtures; do not start Postgres manually.

---

## 4. Database & Shared Data Layer Rules

- Use the repositories and DTOs from `packages/shared_data_layer`. Never duplicate schema definitions.
- Integration tests that touch the DB must import the shared fixtures (see `packages/shared_data_layer/tests/conftest.py`) and leverage Testcontainers as described in that package’s AGENTS guide.
- When new persistence needs arise in this service, add repository helpers inside `services/agent-api` but lean on the shared data layer for actual DB access over direct SQL.
- If a task requires schema or repository changes, you may edit `packages/shared_data_layer` directly—just keep its AGENTS guide in mind and run the package’s test suite before finishing.
- You can install the shared data layer in dev mode with `uv add -e ../packages/shared_data_layer`.

---

## 5. Research & Source Hygiene

- **Default to external validation**: before implementing cache, telemetry, or LangGraph patterns, hit Context7 or the public docs (e.g., LangGraph, Valkey, Prometheus). Capture citations in the plan file.
- Summarize the source + link for any novel approach (e.g., new `uv` workflow, telemetry pattern). This matches builder.io’s AGENTS best practice: “lead with concrete references and file paths; iteratively add rules when issues reoccur.”

---

## 6. Runtime Safety, Permissions & Tooling

Allowed without additional approval (within this repo):
- Reading/listing files.
- Running the commands in §3 via `uv run`.
- Editing files under `services/agent-api` and `docs/*` referenced by the current task.

Ask the user before:
- Modifying other packages (unless the task explicitly requires cross-package changes).
- Adding heavy dependencies or changing deployment infrastructure.
- Running destructive commands (`rm -rf`, database resets outside Testcontainers, etc.).

When stuck, follow the “stuck protocol” from the shared data layer playbook: pause, capture the issue in the plan, reproduce with a minimal test, research externally, then proceed.

---

## 7. Task Tracker Lifecycle

1. Plan file approved → create tracker (`TASK_<id>_TRACKER.md`).
2. Update tracker after each sub-step (use checkboxes + timestamps or brief notes).
3. At the end of the task:
   - Ensure all steps are checked.
   - Copy any important retrospectives into the final response or task doc.
   - Delete the tracker file **and** the associated plan (`TASK_<id>_PLAN.md`) to keep the workspace clean (document the deletions in your summary).
4. Update the Epic 3 checklist entry corresponding to the completed work, including cross-links to code/doc changes or explaining any reordering/removal.

---

## 8. Definition of Done

A task is complete only when:
1. Plan + tracker workflow followed (both files removed afterward).
2. All required docs/tests/code changes are committed.
3. Commands in §3 succeeded locally; include summaries in the final response.
4. `services/agent-api/epic-03/CHECKLIST.md` reflects the new status.
5. Relevant docs (e.g., `docs/agents/implementation.md`, `docs/overview/system_architecture.md`, `services/agent-api/epic-03/subgraph-acceptance.md`) are updated when the task touches those areas.

Stick to these rules and every future agent—no matter how fresh the session—will be able to deliver deterministic results without rediscovering context.
