# Task: Enforce Text-to-SQL Execution for All Numerical Answers

## Context
- **Repo**: `housing-microservices`
- **Current mode**: Reduced-scope production stack using `.env.prod`, LocalStack by default (`USE_LOCALSTACK=1`), real OpenAI/Voyage keys.
- **Relevant services**: `services/agent-api`, `auth-service`, `user-service`, `db-init`, LocalStack.
- **Existing flow**:
  - Router node (`services/agent-api/src/nodes/router/router_node.py`) already detects quantitative prompts and can route to `numerical_subgraph`.
  - Numerical planner still allows the LLM to answer directly without running the Polars/SQL executor.
  - Production runbook and smoke script expect quantitative questions to be grounded in seeded docs (voucher memo, KPI table, ledger, stability overview).
- **Goal**: Guarantee every response containing numeric reasoning is produced exclusively via the text-to-SQL pipeline (Polars mission planner + executor). The LLM must never perform arithmetic in freeform text.

## Problem Summary
Recent SSE traces show:
- Router marks prompts as `route="numerical"`, but execution jumps straight from router to `informational_answer_synthesizer`.
- No `numerical_scope_builder`, `polars_table_loader`, or `sql_executor` events appear.
- Answers cite documents but do not include structured SQL results, so math still occurs inside the LLM.

We need an engineering plan to:
1. Remove all “direct answer” fallback paths once a prompt includes numeric intent.
2. Force the numerical subgraph to always emit at least one SQL query executed by Polars.
3. Provide validation, telemetry, tests, and documentation so future agents/operators can verify the behavior.

## Required Changes
Break the work into the following sub-tasks:

1. **Router Hard Gate**
   - Update `router_node.py` to treat any detected numeric signal (KPI tables, percentages, thresholds, “compare”, “sum”, etc.) as a *mandatory* numerical route.
   - Emit metadata flag (e.g., `requires_sql=True`) that downstream nodes can enforce.
   - Extend router unit tests under `services/agent-api/tests/router/test_router_node.py` with new fixtures covering simple additions and percentage comparisons.

2. **Numerical Planner Enforcement**
   - Files: `services/agent-api/src/nodes/numerical/*.py` (planner, table builder, sql executor).
   - Remove / bypass “direct response” branches. If planner cannot build a table, surface an explicit failure so the run aborts instead of falling back.
   - Update planner prompt strings to forbid LLM math: “You MUST return a SQL query over the provided table specs; never perform arithmetic yourself.”
   - Ensure every planner output includes:
     - `table_specs` referencing hydrated doc chunks.
     - `sql_queries` referencing those tables.
   - When the `requires_sql` flag is set, short-circuit the flow if `sql_queries` is empty.

3. **Polars Execution Guarantees**
   - Ensure the SQL executor always runs inside a threadpool + Polars DataFrames (existing infra). Add logging (`logger.info`) with table row counts + SQL text so ops can confirm execution.
   - Surface executor outputs (`table_results`) back into `PromptRunResult` for auditing.

4. **Guardrails in Answer Synthesizer**
   - Modify `informational_answer_synthesizer` (and any other terminal node) to check for the presence of `numerical_trace` when `requires_sql=True`.
   - If missing, raise a recoverable error (to retry) or fail the prompt with a clear message (“Numeric response rejected: no SQL trace present”).
   - Include SQL result snippets in the final answer citations (e.g., mention derived values with `[SQL_RESULT]` tag).

5. **Telemetry & Reporting**
   - Update `reporting.py` to display SQL query summaries and table row counts per prompt.
   - Emit metrics (e.g., `numerical.sql.executed=1`, `numerical.sql.rows=...`) using existing telemetry hooks.

6. **Documentation**
   - `docs/runbooks/prod_setup.md`: note that all numeric answers now rely on the Polars text-to-SQL path; explain how to confirm via SSE/logs.
   - `docs/examples/prod_sse_walkthrough.md`: refresh SSE transcript to show `numerical_scope_builder`, `sql_executor`, etc.
   - README or runbook section describing how to interpret SQL trace outputs in `prod_sample_run.json`.

7. **Samples/Seed Data**
   - Ensure seeded documents still cover scenarios requiring addition/averages so SQL path returns meaningful answers (already true, but verify).

## Testing Plan

### Environment Setup
```bash
cd /home/nubol23/Desktop/Codes/housing-microservices
set -a && source .env.prod && set +a
```

### Unit Tests
- Use the service virtualenv (`services/agent-api/.venv`).
```bash
cd services/agent-api
. .venv/bin/activate
pytest tests/router/test_router_node.py
pytest tests/numerical/test_numerical_subgraph.py   # add/extend as part of work
```

### Integration / Smoke
1. Bring up the reduced stack:
   ```bash
   COMPOSE_PROFILES=reduced,ops docker compose --profile reduced up -d --build
   ```
2. Run the prod smoke script (real tools, LocalStack or AWS depending on `.env.prod`):
   ```bash
   ./scripts/prod_smoke_check.sh
   ```
   Confirm `prod_sample_run.json` now includes `sql_queries` and `table_results`.
3. Manual SSE verification:
   ```bash
   TOKEN=$(curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
     -H 'Content-Type: application/json' \
     -d "{\"login\":\"$PROD_DEMO_EMAIL\",\"password\":\"$PROD_DEMO_PASSWORD\"}" | jq -r .access_token)

   curl -N -H "Authorization: Bearer $TOKEN" -H 'Accept: text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{
           "thread_id":"<conversation-id>",
           "message":{"type":"user","content":"Group KPI values by city and call out whoever exceeds 80."},
           "constraints":{"country_code":"USA","auto_attach_base_docs":false}
         }' \
     "$AGENT_BASE_URL/v1/chat"
   ```
   Expect events for `numerical_scope_builder`, `polars_table_loader`, `sql_executor`, and final answer referencing SQL output.

### Logs
- Tail agent logs to confirm SQL execution:
  ```bash
  COMPOSE_PROFILES=reduced,ops docker compose logs -f agent-api | grep sql_executor
  ```

## Acceptance Criteria
- Any numeric-related prompt (even “What is 40 + 2 from the KPI table?”) triggers `route=numerical`.
- The SSE/event log shows numerical nodes executing SQL.
- `prod_sample_run.json` stores `sql_queries` + `table_results`.
- Tests covering router, planner, executor behavior pass.
- Documentation explains how to confirm SQL-backed answers and how to refresh tokens for SSE.
