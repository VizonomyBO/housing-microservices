# Task: [Completed] Rewrite Docs/Prompts for the Revamped Architecture

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root. Use service-specific AGENTS when touching those areas.
The agent must commit the changes before terminating the task.
Once the task is done, mark this as completed in the title

## Objective
- Replace legacy documentation/prompts/runbooks with materials that reflect the simplified text-only voyage-context-3 stack, ReAct agent with Pyodide tooling, and new dev/prod workflows.

## Scope
- Update README/INDEX/QUICKSTART + `docs/overview/*`, `docs/agents/*`, `docs/runbooks/*`, setup guides, and testing guides to match the new services, compose profiles, deployment script, and ingestion-first flow; include Pyodide sandbox constraints (Wasm, no FS, httpx installs).
- Remove or archive deprecated epics/task prompts/notes referencing Step Functions/Lambda ingestion, graph RAG/planner, cache/rate-limiter/reduced-scope modes, telemetry, or Valkey; ensure remaining docs explicitly deprecate graph tables and legacy artifacts rather than implying support.
- Refresh smoke/test instructions (`scripts/prod_smoke_check.sh` docs, test-api notes) for the synchronous ingestion path and new retrieval agent.
- Update any agent prompt templates/eval docs to align with the ReAct tooling and advanced RAG techniques.

- Ensure references to memory bank/AGENTS are intact where relevant.

## Deliverables
- Documentation set free of legacy Step Functions/Lambda/cache/graph references and aligned with the new architecture, including updated prompts/eval guidance.
- Clear deprecation notes for retained-but-unused schema artifacts (graph tables, non-text chunk fields) and removed modes.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`, service-specific AGENTS as applicable
