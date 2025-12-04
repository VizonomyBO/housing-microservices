# Reduced-Stack SSE Walkthrough

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
| 12–13 | `router`            | Chooses the `informational` subgraph with 0.6 confidence once guardrails pass.                  |
| 14–15 | `informational_answer_synthesizer` | Spends ~8 seconds synthesizing the answer, citing policy memo, KPIs, and ledger figures. |
| 16 | `done`                | Emits the final markdown answer plus the four citations used.                                   |

Full raw SSE payloads are shown below for reference:  
<details>
<summary>Raw SSE Log</summary>

```
(see logs captured on 2025-12-04T05:48:07Z with request_id viz-0fe5c0f414bb...)
```

</details>

## 3. Takeaways

- Expect the same node order whenever you ask a multi-document policy/KPI question: `input_normalizer → attachment_scope_loader → graph_retriever → router → informational_answer_synthesizer`.
- If you want to watch a different scenario, re-run `./scripts/prod_smoke_check.sh` first so you have the latest `thread_id`, then replace the question in the curl body.
