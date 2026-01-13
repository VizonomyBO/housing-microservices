# Prod Manual Smoke (Attach Existing Document)

Use this when you want a fast prod smoke that reuses an already-active document instead of waiting for a new ingestion. It creates a conversation, attaches the doc, and asks the four FSAP questions (including the pyodide_sandbox code step).

## Prereqs
- Prod env vars loaded (via `.env.prod` or `scripts/use_env.sh prod`).
- `curl`, `jq`, `python3` available locally.
- An active `document_id` in prod (recommended: the FSAP upload `a91ff5f5-69ed-4615-9311-003b44003df5`, active 2026-01-13). The script can ingest a new file if you pass `--upload-file`, but that path is slow in prod.

## Run (reuse existing doc)
```bash
env_file=$(scripts/use_env.sh prod)
DOC_ID=a91ff5f5-69ed-4615-9311-003b44003df5 \
  ./scripts/prod_manual_smoke.sh --env-file "$env_file" --doc-id "$DOC_ID" \
  --smoke-output /tmp/prod_manual_smoke_$(date +%s).json
```

## Run (ingest a new file if needed)
```bash
env_file=$(scripts/use_env.sh prod)
UPLOAD_FILE="services/agent-api/evals/data/MEX_2016_Mexico Financial Sector Assessment Program Housing Finance.pdf" \
  ./scripts/prod_manual_smoke.sh --env-file "$env_file" --upload-file "$UPLOAD_FILE"
```
Notes:
- Ingesting in prod is synchronous and can take a while; the script polls `/v1/documents` until the doc is active.
- `STAMP_UPLOAD=1` by default in prod to avoid dedupe; set `STAMP_UPLOAD=0` to disable stamping.

## Output
- JSON report path is shown at the end (default `/tmp/prod_manual_smoke_<timestamp>.json`). It includes the conversation payload, attachments response, and all four chat responses.

## Tunables
- `DOC_ID` / `--doc-id`: reuse an existing active doc (fastest path).
- `UPLOAD_FILE` / `--upload-file`: ingest first, then attach.
- `SMOKE_COUNTRY_CODE`, `SMOKE_TAG`, `SMOKE_NAMESPACE`, `SMOKE_OUTPUT`, `STAMP_UPLOAD` for minor tweaks.
