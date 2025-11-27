# Data Layer Gap Analysis & Implementation Plan (Updated 2025-11-26)

This document captures the remaining work required for `packages/shared_data_layer` to fully meet the design described in `docs/data/schema_and_persistence.md`. It also records key architectural decisions already taken so new contributors have full context.

> **Completed structural work**
>
> - The migration history was consolidated into `000000000001_initial.py`, which now contains the complete schema (documents, retrieval, conversations, knowledge graph, workflow, etc.) plus helper functions (base-doc refresh, graph rollups, workflow stored procedure).
> - Row-Level Security and database policies were intentionally removed. The project relies on database authentication (user/password) plus integrity constraints and repository/ORM logic for enforcement.
> - Refresh/maintenance logic moved from triggers into the ORM/event layer (`shared_data_layer/db/events.py`, `maintenance.py`, repository helpers). Only inexpensive hash-sync triggers remain.
> - LTREE support uses a custom shim (`shared_data_layer/db/ltree.py`) so Alembic autogenerate stays clean even without `sqlalchemy_utils`.
> - Retrieval chunks enforce deterministic partition keys (`country_code`), and helper functions ensure referencing tables inherit the correct partition key.
> - The validation loop (`ruff format`, `ruff check --fix`, `ty check`, full `pytest`) passes; the only known Alembic warning is the computed-column notice for `chunks.text_tsv`.

The sections below focus **only on outstanding work**. Each includes context (“why”), the required implementation tasks (“what/how”), and references to existing code or tests where helpful.

---

## 1. Documents, Ingestion, and Conversation Attachments

### Current State
- Lifecycle fields, deduplication constraints, and soft-delete semantics are implemented (`documents` model + migration).
- `ingestion_jobs` and `artifacts` follow the documented schema, including ENUM constraints, `page_range`, metadata columns, and lightweight hash-sync triggers.
- The full conversations domain exists (conversations/messages/tool-calls/citations/checkpoints) with composite `conversation_documents` PK, ORM-driven refresh hooks, and tests (`tests/test_advanced_logic.py`, repository suites).

### Remaining Work
1. **Partitioned base-document cache**
   - **Why**: Operators need fast country-specific slices for base documents (§5). LIST partitioning allows targeted refreshes and avoids table scans.
   - **What/How**: Convert `base_documents_by_country` into a LIST-partitioned table or MV on `country_code`. Provide helper functions to refresh specific partitions (or all) and add catalog tests (`pg_partitioned_table`) verifying partitions exist.

2. **Attachment/dedup regression tests**
   - **Why**: The constraints exist but we lack tests that assert canonical-name collisions and chat-reference guardrails behave as expected.
   - **What/How**: Add async tests (likely under `tests/test_missing_elements.py`) that intentionally violate canonical-name uniqueness, base-doc scope rules, and verify `active_chat_refs` stays non-negative when `deleted_at` toggles.

3. **Documentation**
   - **Why**: Clients must understand that conversation attachment enforcement now happens via ORM hooks—not RLS.
   - **What/How**: Update README/schema docs explaining the contract for `conversation_documents`, dedup constraints, and when to call the refresh helpers.

---

## 2. Retrieval Corpus & Telemetry

### Current State
- `chunks` now include all documented fields (position, chunk_type enum, image/table payloads, bbox, token checks, generated `text_tsv`, pgvector embeddings). Factories generate deterministic embeddings.
- `chunk_metrics`, `retrieval_runs`, and the `ActiveChunk` view match the design; tests cover standard scenarios.
- Content-hash synchronization is handled by a lightweight trigger; cache refreshes happen via ORM hooks.

### Remaining Work
1. **Country partitioning + indexes**
   - **Why**: Design requires LIST partitioning on `country_code` with supporting GIN/vector/BRIN indexes for high-volume retrieval workloads.
   - **What/How**: Partition `chunks` by `country_code`, add GIN index on `text_tsv`, and create pgvector/BRIN indexes per design. Update migrations and add catalog tests (`pg_indexes`, `pg_partitioned_table`) to verify presence.

2. **Telemetry/audit indexes**
   - **Why**: Auditing `retrieval_runs.document_scope` (JSON) needs indexes to avoid sequential scans.
   - **What/How**: Add expression/GIN indexes (e.g., `GIN (document_scope jsonb_path_ops)`) and document expected filters.

3. **Active view refresh semantics**
   - **Why**: We rely on ORM hooks for refreshes; we still need a helper/test proving inactive documents disappear promptly when status changes.
   - **What/How**: Provide a repository helper (or explicit instruction) to re-run the refresh query and add regression tests verifying stale chunks are removed.

---

## 3. Async Insights (Pillar Answers)

### Current State
- TIMESTAMPTZ timestamps, published-only uniqueness, and `(pillar_answer_id, chunk_id)` uniqueness are implemented and tested.

### Remaining Work
1. **External identity contract**
   - **Why**: The design assumes user/private scopes always include `owner_user_id`. Without validation, we can create orphaned data.
   - **What/How**: Add Pydantic validators/repository checks enforcing `owner_user_id` presence for non-base scopes, document the rule, and add regression tests.

2. **Regional index**
   - **Why**: Regional queries over published answers need an index on `(country_code, pillar_name)`.
   - **What/How**: Add a partial index filtered to `status='published'` in the migration and verify via catalog tests.

---

## 4. Knowledge Graph Domain

### Current State
- Entities have deterministic keys, ISO-3 country codes, scope-aware unique indexes, and a GIN index on `labels`.
- Edges/evidence enforce cascade behavior, numeric fidelity, and INT4RANGE offsets; repository methods refresh materialized views and tests cover these flows.

### Remaining Work
1. **Partition + strict geography**
   - Partition `graph_entities` by `country_code` and enforce `country_code IS NOT NULL` for base-scope rows. Update ingestion pipelines and add catalog tests.

2. **Performance indexes**
   - Add missing indexes: GIN on `graph_communities.entity_ids`, BRIN on `graph_edges.first_seen_at/last_seen_at`, and pgvector index on embeddings. Verify via catalog queries during tests.

3. **Automated MV refresh cadence**
   - Repository refresh calls work for row-level writes, but bulk ingestion (COPY, ETL) still needs a scheduled refresh. Implement a background task/CLI helper and document expected cadence/failure handling.

4. **Community rollup maintenance**
   - Implement a background job or stored procedure that recalculates community rollups (`entity_ids`, metrics) and add tests validating it works.

5. **Country validation docs/tests**
   - Document the country code rules and add regression tests ensuring base entities without ISO-3 codes fail fast.

---

## 5. Workflow Graphs

### Current State
- Workflow metadata (versions, approvals, change logs) is complete; nodes use LTREE paths and edges reference nodes by UUID.
- The stored procedure (`workflow_nodes_move_subtree`) now enforces depth/cycle constraints with thorough test coverage.

### Remaining Work
1. **LTREE index + depth constraint**
   - Add a `GIST` index on `workflow_nodes.path` and a `CHECK (nlevel(path) <= max_depth)` to ensure depth limits hold even outside the stored procedure. Add regression tests showing direct inserts/updates violating the constraint fail.

2. **Cycle-prevention validation hook**
   - Implement a trigger (or ORM hook) akin to the originally planned `workflow_nodes_validate_path` to prevent inserting nodes beneath their own descendants when bypassing the stored procedure.

3. **Version history tooling**
   - Implement a view or stored procedure summarizing differences between workflow versions for auditability (§3.10) and document how to use it.

---

## 6. Retrieval Cache Integrity & ORM Hooks

> **Validation result:** All current integrity constraints (unique/partial indexes, foreign keys, check constraints) and ORM-driven refresh hooks are covered by the full test suite (`tests/test_advanced_logic.py`, repository tests, automation suites). There are no known inconsistencies or failing scenarios, so no additional task is required here.

---

## 7. Operational Guardrails & Extensions

### Current State
- Required extensions (`pgcrypto`, `ltree`, `pg_trgm`, `vector`) are enabled.
- RLS/policies were intentionally removed in favor of integrity + ORM enforcement.

### Remaining Work
1. **Graph extension decision**
   - Decide whether to enable `pg_graphql`/`apache_age` (as the design once suggested) or document why a pure SQL approach suffices.

2. **Operations guide**
   - Document GC workflows, MV refresh cadence, partition maintenance procedures, and pgvector tuning knobs (`ivfflat.probes`, `work_mem`, etc.) so SREs can operate the system confidently.

3. **Catalog audits**
   - Introduce automated checks (in tests or maintenance scripts) that assert critical indexes/partitions exist after migrations run.

---

## 8. Testing Gaps

### Current State
- Coverage now includes KG repositories, workflow stored procedure scenarios, document/base-doc views, and automation flows. Factories are deterministic, eliminating earlier flaky tests.

### Remaining Work
1. **Catalog assertions**
   - Add helper utilities/tests querying `pg_indexes`, `pg_partitioned_table`, etc., to confirm new indexes/partitions exist once implemented.

2. **Constraint-regression tests**
   - After completing the partition/index tasks, add tests that intentionally violate each new constraint and assert the expected errors.

3. **End-to-end ingestion**
   - Expand the suite with a smoke test that runs document ingestion → chunk creation → knowledge-graph enrichment to ensure ORM-driven refresh hooks keep caches/materialized views up-to-date.

---

## Next Steps Summary

1. **Partitioned & Indexed Storage**: Implement LIST partitioning and the remaining indexes for base documents, retrieval chunks, and knowledge graph entities, accompanied by catalog assertions.
2. **Workflow & KG Guardrails**: Add LTREE path constraints, validation hooks, automated MV refresh cadence, and community rollup maintenance.
3. **Identity & Documentation**: Enforce/document the pillar answers identity contract, base-doc partition strategy, and the operational runbook (refresh cadence, maintenance tasks, extension decisions).
4. **Testing Enhancements**: Add catalog assertions, constraint-regression tests, and end-to-end ingestion coverage to guarantee integrity constraints and ORM-driven refresh hooks remain solid as the schema evolves.
