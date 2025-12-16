# Task: Rebuild Agent API to ReAct Tool Stack (No Cache/Rate Limit)

Follow `.kilocode/rules/memory-bank-instructions.md`, `AGENTS.md`, and `services/agent-api/AGENTS.md` before editing; create/update a plan + tracker in the repo root per instructions.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Replace the LangGraph planner/cacher with a lean ReAct agent and tool suite (retrieval, rerank, attachment/document tooling, Pyodide code execution) using voyage-context-3 + rerank-2.5, with advanced RAG techniques (HyDE/HyPE, contextual headers, fusion retrieval, filtering).

## Scope
- Remove Valkey/rate-limiter/reduced-scope dependencies from `services/agent-api` (settings, HTTP deps, runners, tests, Dockerfile/uv/pyproject).
- Eliminate graph-RAG planner/nodes/guardrails and conversation summary cache reliance; preserve citation quality and attachment gating.
- Implement ReAct loop (per LangGraph ReAct patterns) with tools: BM25+vector retrieval over Postgres/pgvector, rerank utility, doc status/activation, attachment management (list/create conversations, bulk attach/detach, owner nullable/“0000” shared, delete doc + S3/chunks), and PyodideSandboxTool (stateful optional, network installs via httpx; no filesystem).
- Align models/config with voyage-context-3 (default 1024 dims, allow 256/512/2048), rerank-2.5, and ingestion’s synchronous text-only pipeline.
- Update prompts/evals/tests to the new ReAct behavior; ensure no cache/rate-limit envs remain; keep fail-fast dependency handling.

## Deliverables
- Updated Agent API codebase with ReAct agent + tool modules and Pyodide sandbox wired; Valkey/rate-limit/reduced-scope removed from runtime/tests/config.
- Retrieval stack using voyage-context-3 embeddings + rerank-2.5 with advanced RAG strategies implemented.
- Updated HTTP layer/specs (chat/SSE, attachments, conversations) consistent with new tools; docs/tests adjusted accordingly.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`, `services/agent-api/AGENTS.md`
