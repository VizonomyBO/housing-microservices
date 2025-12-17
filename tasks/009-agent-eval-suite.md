# Task: Design OOP + Pytest Agent Eval Suite (API-Driven)

Follow `.kilocode/rules/memory-bank-instructions.md`, `AGENTS.md`, and service-specific AGENTS before editing; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Research and design a maintainable, object-oriented pytest-based evaluation suite for the Agent API, exercising the ReAct tool stack end-to-end via HTTP (chat/SSE, attachments, retrieval/rerank paths).

## Scope
- Study current Agent API behavior, tools, and schemas to define eval targets (grounding, citation quality, attachment gating, HyDE/fusion retrieval expectations).
- Propose an OOP test harness structure (fixtures, client abstractions, scenario objects) that minimizes duplication and cleanly layers setup/teardown over the API surface.
- Identify data/fixtures needed (seed docs, attachments, owner variants including sentinel/nullable owners) and how to provision them via existing ingestion/upload flows.
- Recommend assertions/metrics for evals (accuracy proxies, rerank ordering, citation alignment, latency budgets) and how to parametrize them for voyage-context-3 defaults.
- Outline how to integrate the suite into CI (markers, required env, data seeding) without introducing mocks on production paths.

## Deliverables
- A written design/plan in-repo describing the OOP/pytest harness layout, fixtures, and scenarios for agent evals.
- Proposed file/fixture structure and marker strategy ready for implementation, aligned to the text-only voyage-context-3 stack and ownership rules.
- Updated references/checklist in tasks if needed for future implementation work.

## References
- `.kilocode/rules/memory-bank/*.md`
- `docs/requirements_revamp.md`
- `AGENTS.md` and `services/agent-api/AGENTS.md`
