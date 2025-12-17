# Reduced-Stack SSE Walkthrough

> **Archived (pre-revamp):** References reduced-stack/demo headers and Valkey-related metadata. The current stack is ingestion-first with no reduced-scope or cache layer; use the standard smoke commands in `docs/runbooks/prod_setup.md`.

This note shows how to tail `/v1/chat` as Server-Sent Events (SSE) when you ask the “advanced reasoning” question documented in the production runbook.

## 1. Command Recap

```bash
set -a && source .env.prod && set +a
TOKEN=$(
  curl -sS -X POST "$AUTH_BASE_URL/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"login\":\"$PROD_DEMO_EMAIL\",\"password\":\"$PROD_DEMO_PASSWORD\"}" \
  | jq -r '.access_token'
)

curl -N -H "Authorization: Bearer $TOKEN" \
     -H 'Accept: text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{
           "thread_id":"f233848f-8832-5969-9ca0-877f9e2af652",
           "message":{
             "type":"user",
             "content":"Using the guardrail memo, District 9 ledger, and KPI dashboard, identify which zones exceed the 80-point trigger and outline a two-step plan that pairs arrears relief with voucher guardrails for those renters. Cite KPI values and dollar figures."
           },
           "constraints":{"country_code":"USA","auto_attach_base_docs":false}
         }' \
     "$AGENT_BASE_URL/v1/chat"
```

- The `thread_id` is the conversation ID printed by `./scripts/prod_smoke_check.sh` (e.g., `f233848f-8832-5969-9ca0-877f9e2af652`).
- The prompt forces RAG, the KPI table lookup, and the policy/ledger docs, so every major node emits telemetry.

## 2. Event Highlights

| ID | Event Type            | Notes                                                                                           |
|----|-----------------------|--------------------------------------------------------------------------------------------------|
| 1  | `meta`                | Confirms reduced-scope real-tool mode, request ID `viz-0fe5c0f4…`.                               |
| 2  | `demo_mode_skipped`   | Reminds you Valkey/rate limits are enabled (demo flag is just metadata).                         |
| 3–4 | `task_start`/`task_end` (`input_normalizer`) | Normalizes the request, detects `language=tl` due to sample text, and reports attachments. |
| 5–6 | `attachment_scope_loader` | Loads the four seeded documents (policy, guardrails, ledger, KPI dashboard).                  |
| 7–11 | `graph_retriever` → `graph_summarizer` | Attempts to pull cached graph context; no entities exist so the summarizer falls back.    |
| 12–13 | `router`            | Sets `route=numerical` with `requires_sql=true` after spotting KPI/threshold cues.              |
| 14  | `numerical_text_to_sql`   | Selects the KPI table, emits `table_specs`, and logs the Polars SQL in the metadata.         |
| 15  | `numerical_polars_executor` | Runs the SQL in a threadpool, logs the SQL text + row counts, and emits `sql_cache_bypass=true` plus `numerical.sql.*` metrics. |
| 16  | `numerical_result_validator` | Confirms row bounds + schema and attaches the table preview artifacts.                    |
| 17  | `informational_answer_synthesizer` | Verifies the SQL trace is present, adds the `[SQL_RESULT]` citation, then drafts the prose answer. |
| 18 | `done`                | Returns the final answer plus `requires_sql`, `sql_queries`, `table_results`, and citations.     |

Full raw SSE payloads are shown below for reference:  
<details>
<summary>Raw SSE Log</summary>

```
(see logs captured on 2025-12-04T05:48:07Z with request_id viz-0fe5c0f414bb...)
```

</details>

## 3. Takeaways

- Expect the same node order whenever you ask a multi-document policy/KPI question: `input_normalizer → attachment_scope_loader → graph_retriever → router (requires_sql) → numerical_scope_builder → numerical_text_to_sql → numerical_polars_executor → numerical_result_validator → informational_answer_synthesizer`.
- The `done` payload now echoes the SQL trace (`requires_sql`, `sql_queries`, `sql_row_count`, `table_results`). Compare these fields against `prod_sample_run.json` when you want to double-check that the numbers in the prose answer match the executor output.
- If you want to watch a different scenario, re-run `./scripts/prod_smoke_check.sh` first so you have the latest `thread_id`, then replace the question in the curl body.
