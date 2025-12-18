# [Completed] Task: Design OOP + Pytest Agent Eval Suite (API-Driven)

Follow `.kilocode/rules/memory-bank-instructions.md`, `AGENTS.md`, and service-specific AGENTS before editing; create/update a plan + tracker in the repo root.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Research and design a maintainable, object-oriented pytest-based evaluation suite for the Agent API, exercising the ReAct tool stack end-to-end via HTTP (chat/SSE, attachments, retrieval/rerank paths).
- The eval suite should be designed to run against the prod database, upload the documents at `/home/nubol23/Desktop/Codes/MEX` and `/home/nubol23/Desktop/Codes/ARG` without a user assigned (effectively being shareable) and use them for all the eval tests.
- The eval tests must take the capabilities of the agent to the limit to check all it's potential
- We must leverage existing libraries for the metrics and all.
- I want it to be oop friendly to be able to create scenarios with code and run the tests with pytest.
- Research the web on best practices to build the eval suite with llm as a judge. Use gpt-5.1 with reasoning effor high as the judge for all metrics

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

## Status
- Completed via `docs/testing/llm_eval_suite_proposal.md` (OOP harness layout, metrics/judge defaults, MEX/ARG ingestion plan, CI/markers).

## References
- `.kilocode/rules/memory-bank/*.md`
- `docs/requirements_revamp.md`
- `AGENTS.md` and `services/agent-api/AGENTS.md`
