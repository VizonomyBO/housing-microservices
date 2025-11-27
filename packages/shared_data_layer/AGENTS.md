# Agent Guide – Shared Data Layer (Updated November 2025)

This document is the **authoritative playbook** for agents touching `packages/shared_data_layer`. The system is still pre-production, but the schema and business rules are mature—treat every change as production-grade.

- ✅ **Current architecture status**: The migration stack has been collapsed into a single `000000000001_initial.py`, LTREE support uses the in-repo shim, and refresh/maintenance logic is handled in ORM/event helpers (not triggers/RLS). Row-Level Security was intentionally removed; data integrity relies on constraints plus repository logic.
- 📋 **Open work**: Follow the per-scope task briefs in `packages/shared_data_layer/TASK_6_PLAN.md`, `TASK_9_PLAN.md`, and `TASK_11_PLAN.md`. Each file isolates a single unit of work so agents can deliver one task per session.
- 🧭 **Working directory rule**: Always run commands from `packages/shared_data_layer`. Start each shell session with `cd packages/shared_data_layer` so dependencies, virtualenv paths, and tests resolve correctly.
- 🧪 **Containers**: Never start Docker manually. Tests spin up pgvector via Testcontainers; let pytest manage lifecycle.

---

## 1. Cognitive Workflow (Plan → Act → Verify)

1. **Plan**
   - Read the user request, then skim the relevant `packages/shared_data_layer/TASK_*_PLAN.md` file(s) and recent diffs to understand context.
   - Write/update a lightweight task plan (e.g., a temporary `TASK_PLAN.md` in the repo root) before editing code. Remove the scratch file once the work is complete.
2. **Research**
   - If you are unsure about `ltree`, `pgvector`, `polyfactory`, or any library, immediately consult Context7/serper. Do not guess.
   - Capture relevant docs/links in your plan.
3. **Act**
   - Make atomic commits per subsystem (models vs. migrations vs. tests).
   - Keep edits scoped to the data layer; do not wander into service packages unless explicitly asked.
4. **Verify**
   - Run tests as soon as a meaningful unit of work is done.
   - Never accumulate TODOs “to fix later”.

**Stuck protocol** (3 failed attempts on the same issue):
1. Stop coding.
2. Create `tests/reproduce_issue.py` with the minimal failing case.
3. Research externally (Context7/serper) with targeted queries.
4. Document the hypothesis in your plan, then try the new approach.

---

## 2. Environment & Commands

All commands below assume `pwd == packages/shared_data_layer`.

| Purpose | Command |
| --- | --- |
| Install deps | `uv sync --all-extras` |
| Formatter | `./.venv/bin/ruff format .` |
| Lint (auto-fix) | `./.venv/bin/ruff check --fix .` |
| Type check | `./.venv/bin/ty check .` |
| Full test suite | `./.venv/bin/pytest -n auto` |
| Single test | `./.venv/bin/pytest tests/path/to/test.py::test_name` |
| Migration smoke test | `./.venv/bin/pytest tests/test_migrations.py -s` |

**Testing best practices (per PostgreSQL/Testcontainers community guidance)**
- Run targeted tests before the entire suite to tighten feedback loops.
- Use `-n auto` for the full run, but disable parallelism when debugging race conditions.
- Capture flaky failures with `pytest -k pattern --maxfail=1 -vv`.

---

## 3. Definition of Done

You are finished only when all of the following succeed locally (no warnings except the known `chunks.text_tsv` computed column notice):

1. `./.venv/bin/ruff format .`
2. `./.venv/bin/ruff check --fix .`
3. `./.venv/bin/ty check .`
4. `./.venv/bin/pytest -n auto`

Attach command output summaries in your final response; do not rely on CI.

---

## 4. Architecture Notes & Patterns

### Migrations & Database
- Extensions enabled out of the box: `pgcrypto`, `ltree`, `vector`, `pg_trgm`.
- All schema definitions live in `src/shared_data_layer/migrations/versions/000000000001_initial.py`. If you need new schema changes, extend this file unless the task explicitly requires additional revisions.
- Stored procedure `workflow_nodes_move_subtree` takes `(graph_id UUID, source_path ltree, target_parent_path ltree)` and must always cast results back to `ltree` (`... )::ltree`).
- Trigger usage is intentionally minimal. Prefer ORM/event-layer refresh hooks (`shared_data_layer/db/events.py`) when wiring new maintenance tasks.

### ORM & Pydantic
- SQLAlchemy async models cannot lazy-load once the session/loop closes. Always use `selectinload`/`joinedload` in repositories before serializing to Pydantic schemas.
- Deterministic factories (`shared_data_layer/testing/factories/...`) ensure constraint-safe test data—re-use them rather than rolling ad-hoc fixtures.
- LTREE paths use the in-repo shim (`shared_data_layer/db/ltree.py`); do **not** import `sqlalchemy_utils`.

### Testing Infrastructure
- Testcontainers-based `PostgresContainerWithVector` (fsync off, tmpfs) powers all DB tests.
- Fixtures: infrastructure (`event_loop`, `postgres_container`, `engine`) are `session`-scoped; `db_session` is `function`-scoped to guarantee rollback.
- Never call Docker/Compose manually—pytest manages containers.

### Common Pitfalls & Fixes

| Symptom | Likely Cause | Remedy |
| --- | --- | --- |
| `MissingGreenlet` / `DetachedInstanceError` | Lazy load outside async session | Use `selectinload` on repositories |
| `ProgrammingError: column "path" is of type ltree` | Casting omission | Ensure `::ltree` in SQL/SP updates |
| `expected 512 dimensions, not 0` | Empty pgvector in factory/test | Override `embedding` with deterministic list |
| Testcontainers hang | Manual container startup | Stop any local Postgres; rerun via pytest |

---

## 5. Source Map / High-Value Files

- `packages/shared_data_layer/TASK_*_PLAN.md` – scoped backlog describing any remaining schema/infra work (one unit per file).
- `TASK_PLAN.md` (temporary) – per-task scratch plan you create/update (delete when done).
- `src/shared_data_layer/db/models/*` – SQLAlchemy models.
- `src/shared_data_layer/db/events.py` & `maintenance.py` – ORM-based refresh hooks.
- `src/shared_data_layer/migrations/versions/000000000001_initial.py` – single authoritative migration.
- `src/shared_data_layer/testing/*` – Testcontainers fixtures and Polyfactory builders.
- `tests/test_*.py` – broad coverage (views, repositories, automation, stored procedures, migrations).

Keep this guide close and update it whenever major architectural decisions land so future agents inherit an accurate map.
