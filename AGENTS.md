## 1. Always Plan → Research → Act → Verify

### Plan
1. **Create a task-specific plan file** before touching code. Summarize the request, impacted files, risks, and ordered steps referencing the relevant epic task doc. Plans are auto-approved—note that in the file and proceed immediately, then treat the plan as ephemeral (delete it when the task is done).

### Research (prioritize external validation)
- For every open question, **start with web research and Context7 documentation**. Capture the sources (URLs or doc IDs) inside the plan so reviewers see what informed the decisions.
- When using libraries/APIs, read their docs via Context7 or web search before coding. Avoid hallucinations by quoting the reference in commit notes or doc comments when helpful.

### Act
1. **Create a tracker file** for the plan: (no waiting period; every plan is implicitly approved).
2. Mark the ordered steps `[ ]` → `[x]` as you complete each chunk of work. Keep the tracker up to date throughout the task.

### Verify
1. **Run the full test suite** every time you reach a review-ready state.
3. After successful verification, remove both the tracker file and the plan file, then document the commands/output in your final response along with links to affected files.

---

## 2. Environment, Commands & Tools (uv-first)

**Shared automation env (`.venv.tooling`)**
- `scripts/ensure_tooling_env.sh` bootstraps a repo-level uv virtualenv plus `shared_data_layer`/auth-service deps; `scripts/setup_remote_databases.sh` already calls it before running migrations.
- If we later add more automation that needs shared_data_layer (scripted data refreshes, LocalStack DB prep, etc.), point those helpers at `ensure_tooling_env.sh` so they reuse the same environment; currently no other tasks depend on it.

| Purpose | Command | Notes |
| --- | --- | --- |
| Ensure env exists | `uv venv --python 3.13 .venv` | Already created; rerun if `.venv` missing. |
| Install/update deps | `uv sync --all-extras` | Reads `pyproject.toml` / `uv.lock`; adds/updates `.venv`. |
| Add a dependency | `uv add <package>` | Automatically resolves + updates lock. Prefer `uv add --dev` for dev tools. |
| Pin Python version | `uv python pin 3.13` | Writes `.python-version` for reproducible local runs. |
| Lock dependencies | `uv lock` | Re-resolve + refresh `uv.lock`. |
| Run scripts/commands | `uv run <command>` | Ensures the `.venv` + pinned Python are used. |
| Pip-compatible sync | `uv pip sync requirements.txt` | Use when tasks require legacy requirements files. |
| Install CLI tool | `uv tool install <pkg>` / `uvx <tool>` | e.g., `uv tool install ruff`. |

**Standard quality gates (same as shared data layer)**
Run these (via `uv run`) before marking a task complete:

```bash
uv run ruff format .
uv run ruff check --fix .
uv run ty check .
uv run pytest -n auto
```

---

## 3. Database & Shared Data Layer Rules

- Use the repositories and DTOs from `packages/shared_data_layer`. Never duplicate schema definitions.
- Integration tests that touch the DB must import the shared fixtures (see `packages/shared_data_layer/tests/conftest.py`) and leverage Testcontainers as described in that package’s AGENTS guide.
- When new persistence needs arise in this service, add repository helpers inside `services/agent-api` but lean on the shared data layer for actual DB access over direct SQL.
- If a task requires schema or repository changes, you may edit `packages/shared_data_layer` directly—just keep its AGENTS guide in mind and run the package’s test suite before finishing.
- You can install the shared data layer in dev mode with `uv add -e ../packages/shared_data_layer`.

---

## 4. Research & Source Hygiene

- **Default to external validation**: before implementing code, consult Context7 or public docs. Capture citations in the plan file.
- Summarize the source + link for any novel approach (e.g., new `uv` workflow, Compose optimization, rate-limiter fallback). This matches builder.io’s AGENTS best practice: “lead with concrete references and file paths; iteratively add rules when issues reoccur.”

---

## 5. Runtime Safety, Permissions & Tooling

Ask the user before:
- Modifying other packages (unless the task explicitly requires cross-package changes).
- Adding heavy dependencies or changing deployment infrastructure outside the scope of the assigned task.
- Running destructive commands (`rm -rf`, database resets outside Testcontainers, etc.).

When stuck, follow the “stuck protocol” from the shared data layer playbook: pause, capture the issue in the plan, reproduce with a minimal test, research externally, then proceed.

---

## Task-Specific Requirements (Ingestion Reactivation)

- Maintain the per-task plan + tracker files (`TASK_PLAN.md`, `TASK_PLAN_PROGRESS.md`) and keep them in sync with the outstanding steps (enforce attachment safety, LocalStack verification, AWS verification, cleanup/tests).
- For the in-progress AWS smoke work (Step 9), review `notes/aws_step9_status.md` before making changes; it captures the latest commands, evidence paths (`/tmp/aws_smoke_step9/`), and outstanding actions.
- Always run Python tooling via `services/agent-api/.venv` and prefer `uv run …` for formatting, linting, typing, and pytest.
- Compose workflows must support pointing the locally running services at the AWS deployment by sourcing `.env.prod.aws`; LocalStack remains required for verification as well.
- Perform the end-to-end curl walkthrough plus `scripts/prod_smoke_check.sh` in both LocalStack and AWS modes before completion; document commands and evidence in the tracker.
- When AWS resources conflict, re-run Terraform with the provided `ArchaaS/terraform.v2.tfvars` (uses the `vizonomy-v2/dev2` suffix) instead of deleting user-managed infrastructure.
- The remote Postgres host must expose **two** logical databases (`housing` for shared_data_layer/agent-api, `auth_db` for auth-service). Never co-mingle schemas by reusing `auth_db` for agent tables—create/fix the `housing` database instead.
- **Current session constraints (Dec 2024):** user requested we focus on AWS verification (Plan Step 7) while deferring the LocalStack run to a later session, and to leave `TASK_PLAN.md` / `TASK_PLAN_PROGRESS.md` in place after finishing so the next session can resume quickly.
- **Current focus (Feb 2025):** Step 9 is active—rerun the AWS curl walkthrough and `scripts/prod_smoke_check.sh` against the real stack (ignore LocalStack), ensure each upload is unique to avoid dedupe short-circuits, capture command evidence/IDs, and update the tracker while keeping the plan files for future sessions. (Update: Task 14 replaced the Lambda ingestion with a FastAPI service on EC2; `INGEST_BASE_URL` now points to http://52.207.140.87:8085 and smoke has passed through the new service.)
- **State machine + callback handling (Dec 2025):** Preserve the original document upload payload at the start of the Step Functions workflow (e.g., copy it under `$.request`) so optional fields like `callback_url`, `tags`, and `trace_id` remain accessible in later states (DeadLetter, EmitFailureEvent, Finalizer). Reference `$.request.callback_url` instead of the mutable root, aligning with AWS’s `ResultPath` best practices.
- **AWS verification discipline:** The `/tmp/aws_flow.sh` helper uploads a new document on every run. After a timeout or failure, do **not** trigger another upload; keep polling `/v1/documents?content_hash=…`, inspect the existing Step Functions execution (`aws stepfunctions describe-execution …`), and review per-Lambda CloudWatch logs until that execution succeeds or is redriven. Only upload again when inputs change or after we intentionally purge test data.
