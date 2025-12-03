# Reduced E2E Smoke Epic – Checklist

Complete the tasks in order. Each task must follow `services/agent-api/AGENTS.md` (plan → tracker → research → act → verify → finalize). When a task changes the scope of another, update this checklist immediately so future agents don’t duplicate work.

_Run these tasks sequentially via:_ `./run_tasks.sh --epic epic-reduced-e2e`

_Automated loop available:_ `./run_epic_loop.sh --epic epic-reduced-e2e` re-reads this checklist after each run so newly inserted fix tasks are executed automatically.

1. - [ ] [Task 01 — Reduced Stack E2E Test Plan](tasks/task-01-reduced-e2e-plan.md)
2. - [ ] [Task 02 — Scenario Fixtures & Helper Modules](tasks/task-02-fixtures-and-helpers.md)
3. - [ ] [Task 03 — Reduced E2E CLI Automation](tasks/task-03-e2e-cli.md)
4. - [ ] [Task 04 — Compose Wrapper & CI Integration](tasks/task-04-compose-wrapper.md)
5. - [ ] [Task 05 — Documentation & Production Compose Guide](tasks/task-05-docs-and-prod.md)
