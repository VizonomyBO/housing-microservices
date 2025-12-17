# Task: [COMPLETED] Local End-to-End Smoke Script (ingestion → chat)

Follow `.kilocode/rules/memory-bank-instructions.md` and `AGENTS.md`; create/update a plan + tracker in the repo root. Use service-specific AGENTS when touching those packages. The agent must commit the changes before terminating the task. Once the task is done, mark this as completed in the title.

## Objective
- Build a repeatable local script that exercises the full flow: create user → login → fetch profile → upload files from `services/agent-api/evals/data` via the ingestion service → poll until documents are processed → create conversation → attach uploaded docs → ask questions → report/validate responses. Fix the agent/ingestion paths until responses are coherent (no empty/garbled answers).

## Scope
- Local-only flow using `.env.local` (LocalStack, Postgres, auth/user/ingestion/agent-api). Script should source envs and run under `uv run` or plain bash.
- Ingestion must use the FastAPI ingestion endpoint (MarkItDown → voyage-context-3 embeddings). Implement/consume a polling mechanism to wait for `status=active`; if none exists, add one.
- Attach the uploaded eval docs to a new conversation and ask representative questions; capture SSE/blocking responses and assert they are non-empty, grounded, and sensible. If answers fail, adjust prompts/retrieval/agent to fix.
- Emit a concise report (JSON/log) summarizing doc IDs, attachment results, questions, and answers.

## Deliverables
- Script/tooling that runs the full local smoke (user creation → ingestion upload/poll → conversation + attachments → chat) and a minimal README note on usage.
- Any agent/ingestion fixes needed to produce coherent answers with the eval data.

## References
- `docs/requirements_revamp.md`
- `.kilocode/rules/memory-bank/*.md`, `AGENTS.md`
- Updated docs in `docs/runbooks/full_stack_compose.md` and `docs/testing/llm_eval_quality_improvements.md`
