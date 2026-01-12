# Country Profile RAG Tasks (client requirements)

Use this task list for coding agents. Keep the structure (goal → scope → steps → exits) when updating.

## Task 1 — Backfill publication year metadata (do this first)
- **Goal:** Enable reliable `publication_year` filters (>= 2000) on existing corpora.
- **Scope:** `packages/shared_data_layer`, data/backfill script, optional ingestion metadata parsing helper.
- **Status:** Completed (publication_year populated in prod; backfill script documented and rerunnable).
- **Steps:**
  1. Add support in ingestion to accept `publication_year` in upload metadata and persist to `Document.metadata` (and chunks if cheap).
  2. Write a one-off backfill script: derive `publication_year` from `canonical_name`/`source_uri` patterns (e.g., `*_2016_*.pdf`), validate 4-digit year, and update `documents.metadata`.
  3. Dry-run mode (no writes) plus logging of skipped/ambiguous cases; real run should be idempotent.
  4. Document how to run (local/prod) and where to store run logs.
- **Exit criteria:** Existing docs have `metadata.publication_year` populated where derivable; ingestion supports the field for new uploads; script documented and safe to rerun.

## Task 2 — Add report/country-profile retrieval profile
- **Goal:** For report/cache flows, prioritize country > region > global and exclude `publication_year < 2000`; 3k character cap on answers.
- **Scope:** `services/agent-api` retrieval pipeline + agent runner; no new services.
- **Status:** Completed
- **Steps:**
  1. Add a retrieval profile flag (e.g., via `hints`/`constraints`) in `agent/runner.py` and pass it through `retrieve_documents`.
  2. In `RetrievalService`, apply filters (drop <2000 when present) and geo weighting: country *1.3, region (per `REGION_BY_COUNTRY_ALPHA3`) *1.1, global *0.9 (or bucketed ordering).
  3. Enforce 3k-character cap for this profile: set `max_tokens` on the OpenAI call and add a post-trim that preserves `[c#]` markers.
  4. Keep normal chat behavior unchanged; gated by the profile only.
- **Exit criteria:** Profile switch works; answers respect geo ordering and date rule when metadata exists; 3k cap enforced; default chats unaffected.

## Task 3 — Wire profile into report/cache flows
- **Goal:** Ensure report generation and any cached/pre-generated country flows use the new profile.
- **Scope:** `services/agent-api/services/reports.py`, any cache/report entrypoints.
- **Steps:**
  1. Set the retrieval profile/hints for report-generation conversations/threads.
  2. Confirm attached docs for a country include region/global as today; verify ordering comes from the profile.
  3. Add a small verification note or smoke instructions (no full latency requirement).
- **Exit criteria:** Reports and cached country flows use the profile by default; documentation of how to trigger the profile in other consumers.
