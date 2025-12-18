# [Completed] Task: Agent Eval Suite (OOP + Pytest, API-Driven)

## Process Requirements
- Follow `.kilocode/rules/memory-bank-instructions.md`, `AGENTS.md`, and service-specific AGENTS; create/update a plan + tracker in the repo root.
- Commit the changes before terminating the task and keep the title marked as completed when done.

## Prompt
- Design a maintainable, object-oriented pytest evaluation suite for the Agent API that exercises the ReAct tool stack end-to-end via HTTP (chat/SSE, attachments, retrieval/rerank).
- Run against the prod database, uploading the documents at `/home/nubol23/Desktop/Codes/MEX` and `/home/nubol23/Desktop/Codes/ARG` with no user assigned (shareable) and reuse them for all eval tests.
- Use existing libraries for metrics; research web best practices for LLM-judge evals and use `gpt-5.1` with high reasoning effort for all metrics.
- Keep the suite OOP-friendly so scenarios can be composed in code and executed with pytest.

## Test Account
```json
{
  "email": "eval_user@example.com",
  "username": "eval_user",
  "password": "TestPass123!"
}
```

## Documents to Attach
```
Document Name,Document ID
Mexico Low income housing (Main report),0510b240-5b88-4ae4-8678-4a21ac2ed102
Mexico Low income housing (Vol 2),be7724a0-d8a9-4304-b203-857cb79dce2c
Financial Sector Assessment Program,4d18a758-371e-4991-8f0f-bc9545395f4a
Technical Note on Housing Finance,a3f5776b-8a9e-4020-97d9-31a5b01f39f4
Residential Energy Efficiency Programs,bb8b657e-755d-46c5-a52f-e19d09145886
Improving Housing Resilience Report,09c2d186-35bf-44c4-9566-d71424587d0d
FUNHAVIs housing microfinance program,c729798f-d11c-4da8-b249-9d406d43ac19
```

## API Flow (curl templates)
1) Register
```bash
curl -X POST "http://52.207.140.87:5001/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "eval_user@example.com",
    "username": "eval_user",
    "password": "TestPass123!",
    "first_name": "Eval",
    "last_name": "User",
    "country_code": "USA",
    "role": "public"
  }'
```
2) Login and export token
```bash
curl -X POST "http://52.207.140.87:5001/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "eval_user@example.com",
    "password": "TestPass123!"
  }' | jq -r '.access_token'

export ACCESS_TOKEN="<PASTE_ACCESS_TOKEN>"
```
3) Upload document (request presigned URL)
```bash
curl -X POST "http://52.207.140.87:8085/v1/documents/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "MyDocument",
    "source_type": "pdf",
    "country_code": "USA",
    "language": "en",
    "tags": ["local-smoke", "manual-test"],
    "file_size_bytes": 10240,
    "access_scope": "user_private",
    "metadata": {"source": "manual_curl"}
  }'
```
4) Upload file to S3 using returned `upload.url` and `upload.fields`
```bash
curl -X POST "$UPLOAD_URL" \
  -F "key=<value_from_step_a>" \
  -F "AWSAccessKeyId=<value_from_step_a>" \
  -F "policy=<value_from_step_a>" \
  -F "signature=<value_from_step_a>" \
  -F "file=@/path/to/your/file.pdf;type=application/pdf"
```
5) Check ingestion status
```bash
curl -G "http://52.207.140.87:8000/v1/documents" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "page=1" \
  -d "page_size=10"
```
6) Create conversation
```bash
curl -X POST "http://52.207.140.87:8000/v1/conversations" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "country_code": "USA",
    "namespace": "local-smoke",
    "title": "Manual Curl Test",
    "tags": ["test"]
  }'

export CONVERSATION_ID="<PASTE_CONVERSATION_ID>"
```
7) Attach documents
```bash
curl -X POST "http://52.207.140.87:8000/v1/conversations/$CONVERSATION_ID/attachments/bulk" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_ids": ["<PASTE_DOCUMENT_ID>"],
    "visibility": "visible",
    "role": "primary"
  }'
```
8) Chat
```bash
curl -X POST "http://52.207.140.87:8000/v1/chat" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "'"$CONVERSATION_ID"'",
    "message": {
      "type": "user",
      "content": "Summarize the document I just uploaded."
    },
    "constraints": {
      "country_code": "USA",
      "auto_attach_base_docs": false
    },
    "response_mode": "blocking"
  }'
```

## Runtime Note
To run the evals, mount the local docker compose file pointing to the prod DB, run against the Agent API from compose, then tear down the compose app when finished.

## Scope
- Study current Agent API behavior, tools, and schemas to define eval targets (grounding, citation quality, attachment gating, HyDE/fusion retrieval expectations).
- Propose an OOP test harness structure (fixtures, client abstractions, scenario objects) that minimizes duplication and cleanly layers setup/teardown over the API surface.
- Recommend assertions/metrics for evals (accuracy proxies, rerank ordering, citation alignment, latency budgets) and how to parametrize them for voyage-context-3 defaults.
- Outline how to integrate the suite into CI (markers, required env, data seeding) without introducing mocks on production paths.

## Deliverables
- A written design/plan in-repo describing the OOP/pytest harness layout, fixtures, and scenarios for agent evals.
- Proposed file/fixture structure and marker strategy ready for implementation, aligned to the text-only voyage-context-3 stack and ownership rules.
- Updated references/checklist in tasks if needed for future implementation work.

## Status
- Completed via `docs/testing/llm_eval_suite_proposal.md` (OOP harness layout, metrics/judge defaults, MEX/ARG ingestion plan, CI/markers).

## References
- `.kilocode/rules/memory-bank/*.md`
- `docs/requirements_revamp.md`
- `AGENTS.md` and `services/agent-api/AGENTS.md`
