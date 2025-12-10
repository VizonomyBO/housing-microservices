### Task Plan – Conversation Memory Follow-up (auto-approved)

**Request:** Run local tests, verify multi-turn chat history, deploy any new AWS components/config introduced by the conversation-memory hardening work, and fix bugs discovered.

**Scope / Impacted Areas:** services/agent-api (chat routes, infra config, observability), deployment scripts/Terraform under `ArchaaS` if updates are needed, AWS prod stack wiring (.env.prod, compose/ec2 tooling).

**Risks/Constraints:** Avoid destructive AWS actions; respect existing prod data. Approval policy is "never," so prefer safe commands. Keep existing task plan files intact per AGENTS guidance.

**Ordered Steps:**
1. Inventory recent conversation-memory changes vs. deployed state; identify required AWS/config updates.
2. Research deployment hooks/infra (compose, Terraform, ArchaaS) to determine how to roll out Valkey/cache/metrics needs.
3. Run local quality gates (ruff format/check, ty, pytest) from `services/agent-api` and capture results.
4. Run targeted multi-turn chat regression (pytest or CLI) to confirm history continuity.
5. Deploy/wire any missing AWS components or env settings; validate health and chat behavior in prod.
6. Fix issues found and rerun affected tests; update docs/AGENTS if deployment expectations change.

**Research Sources (update as used):**
- LangGraph docs: stateful chat patterns and message history loading (`langgraph/state` and `chat_models` guidance).
- OpenAI Chat Completions docs: multi-turn message arrays preserve context when roles are ordered (`system` + alternating `user`/`assistant`).
