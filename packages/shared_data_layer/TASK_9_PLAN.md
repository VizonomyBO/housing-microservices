# Task 9 – Workflow Guardrails & Version History Tooling

## Goal
Harden the workflow domain so depth constraints are enforced at the table level, prevent manual cycle regressions, and provide an auditable diff summary between workflow versions.

## Subtasks
1. Inspect migration + ORM definitions + tests to understand current guards (depth trigger, stored procedure, version history view).
2. Extend migration + models with:
   - check constraint tying `nlevel(path)` to the owning graph's max depth (likely via helper function),
   - explicit `GIST` index confirmation (double-check naming, ensure downgrade drops it),
   - trigger/function preventing inserts/updates that would move a node underneath its own subtree outside `workflow_nodes_move_subtree`,
   - SQL view or function (plus optional helper) summarizing workflow version diffs in a consumable format.
3. Update ORM/repository helpers (if needed) and docs to describe the new contract.
4. Add regression tests covering:
   - check constraint violation via direct insert/update,
   - cycle-prevention trigger denying invalid parentage,
   - version diff view returning expected rows from synthetic data.
5. Run `ruff format`, `ruff check --fix`, `ty check`, and `pytest -n auto` scoped where possible first.
6. Update `AGENT_TASK_PLAN.md` entry for Task 9 as completed and summarize in final message.

## Notes / Open Questions
- Need to decide on best implementation for check constraint (likely helper function referencing `workflow_graphs.max_depth`).
- Diff view will probably leverage `jsonb_each` over `change_log` or compare adjacent versions via window functions; confirm `change_log` shape in factories/tests.
- Ensure triggers/drop statements appear in downgrade.

## Completion Notes
- Added `workflow_version_max_depth()` helper, `ck_workflow_nodes_path_depth`, and the `workflow_nodes_prevent_cycle` trigger so LTREE paths stay within the graph `max_depth` even during manual SQL updates.
- Introduced the `workflow_version_diffs` view with node/edge deltas plus catalog tests for the new constraint/index/view coverage.
- Expanded README with workflow guardrail documentation.
- Validation: `ruff format .`, `ruff check --fix .`, `ty check .`, `pytest -n auto` (55 passed; only known Alembic/composite PK warnings remain).
