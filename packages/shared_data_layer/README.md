# Shared Data Layer

The `shared_data_layer` package serves as the single source of truth for database models, data access patterns (repositories), and data transfer objects (schemas) for the Housing Microservices project. It is built with **SQLAlchemy 2.0 (Async)**, **Pydantic V2**, and **PostgreSQL** with `pgvector` support.

## Project Structure

The package is organized as follows:

- **`src/shared_data_layer/db/models/`**: SQLAlchemy database models.
    - `users.py`: User management.
    - `documents.py`: Documents, Uploaded Files, Chunks, Artifacts.
    - `agents.py`: Agent runs and telemetry events.
    - `retrieval.py`: Retrieval runs and metrics.
    - `knowledge_graph.py`: Graph entities and edges.
    - `workflow.py`: Workflow definitions and versions.
- **`src/shared_data_layer/repositories/`**: Async repositories for data access.
    - `base.py`: Generic `BaseRepository` with common CRUD operations.
    - `documents.py`, `knowledge_graph.py`, `agents.py`, etc.: Specialized repositories.
- **`src/shared_data_layer/schemas/`**: Pydantic models (DTOs) for API responses and internal data transfer.
- **`src/shared_data_layer/migrations/`**: Alembic migration scripts.
- **`src/shared_data_layer/testing/`**: Testing utilities and factories.
    - `factories/`: Polyfactory classes for generating test data.
    - `containers.py`: Testcontainers setup for PostgreSQL + pgvector.
    - `conftest.py`: Shared Pytest fixtures.

## Installation & Setup

This package is intended to be installed as a local dependency in other services.

### Prerequisites
- `uv` (Universal Python Package Installer)
- PostgreSQL with `pgvector` extension (for local dev without containers)

### Development Setup

This project uses `uv` for all dependency management. We rely on `pyproject.toml` as the single source of truth.

1.  **Install uv** (if not already installed):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Sync Dependencies**:
    This will create the virtual environment and install all dependencies (including dev and test) defined in `pyproject.toml`.
    ```bash
    uv sync --all-extras
    ```

3.  **Activate Virtual Environment** (Optional but recommended for IDEs):
    ```bash
    source .venv/bin/activate
    ```

### Adding Dependencies

To add a new dependency:
```bash
uv add <package_name>
```

To add a dev dependency:
```bash
uv add --dev <package_name>
```

### Deployment (Production)

To install **only** the production dependencies (excluding development tools and test libraries):

```bash
uv sync --no-dev
```
This command installs the packages defined in `[project.dependencies]` and excludes `[dependency-groups]` and `[project.optional-dependencies]`.

### Installation (as dependency)
In your service's `pyproject.toml`:

```toml
[project]
dependencies = [
    "shared-data-layer @ {root:uri}/packages/shared_data_layer",
]
```

## Usage

### 1. Database Connection
Use the provided `create_async_engine` and `async_sessionmaker` from SQLAlchemy.

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from shared_data_layer.db.base import Base

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/dbname"

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

### 2. Using Repositories
Repositories encapsulate data access logic. Always use repositories instead of direct session queries when possible.

```python
from shared_data_layer.repositories.documents import DocumentRepository

async def get_doc(session, doc_id):
    repo = DocumentRepository(session)
    document = await repo.get_document_with_chunks(doc_id)
    return document
```

Uploaded file registrations can be tracked without duplicating document logic:

```python
from shared_data_layer.repositories.documents import UploadedFileRepository

async def register_upload(session, document, storage_uri, content_hash):
    repo = UploadedFileRepository(session)
    return await repo.register_upload(
        document_id=document.id,
        owner_user_id=document.owner_user_id,
        storage_uri=storage_uri,
        byte_size=document.byte_size or 0,
        content_hash=content_hash,
        ingestion_metadata={"stage": "upload"},
    )
```

The repository enforces the `(owner_user_id, content_hash)` deduplication rule while still allowing base (ownerless) uploads to be recorded independently.

Agent run/event telemetry can be logged for observability:

```python
from shared_data_layer.repositories.agents import AgentTelemetryRepository

async def record_agent_activity(session, conversation_id, owner_id, payload):
    repo = AgentTelemetryRepository(session)
    run = await repo.create_run(
        owner_user_id=owner_id,
        conversation_id=conversation_id,
        planner_name="planner.v2",
        document_scope={"country_code": "USA"},
        input_prompt="Summarize housing changes",
    )
    await repo.append_event(
        run_id=run.id,
        event_type="planner.step",
        payload=payload,
    )
    return await repo.get_run_with_events(run.id)
```
### 3. Using Schemas
Pydantic schemas are available for type-safe data handling.

```python
from shared_data_layer.schemas.documents import DocumentRead

# ... inside an API endpoint
return DocumentRead.model_validate(document_orm_obj)
```

## Testing

This package uses `pytest` and `testcontainers` for integration testing against a real database.

### Running Tests
To run the tests for this package:

```bash
# From the package root
.venv/bin/pytest -n auto
```

For detailed agent instructions and quirks, see [AGENTS.md](AGENTS.md).

### End-to-End Ingestion Smoke Suite

The ingestion pipeline smoke tests live in `tests/test_end_to_end_ingestion.py`. They stitch together document ingestion, chunk activation, and knowledge-graph rollups, so they are **opt-in** and default to `skip`. Run them explicitly with the `--end-to-end` flag:

```bash
.venv/bin/pytest --end-to-end tests/test_end_to_end_ingestion.py -n 0
```

The flag can also be combined with a regular run (e.g., `.venv/bin/pytest --end-to-end -n auto`) when you want the suite included in CI.

## Identity & Ownership Contract

- `owner_user_id` is now flexible: non-base documents may be ownerless or use the system sentinel `00000000-0000-0000-0000-000000000000`; base documents may also use the sentinel or stay `NULL` but still require an ISO-3 `country_code` that propagates to children.
- **Conversation attachments**: Base-scope documents can only be attached to conversations that share the same ISO-3 `country_code`. `DocumentRepository.attach_to_conversation(...)` enforces this guardrail and raises a `ValueError` if the conversation or document are missing a country or the values do not match. Service/API layers should surface that error to clients so users understand why the attachment failed.
- Pydantic schemas expose ISO codes via the `CountryISOAlpha3` enum (`shared_data_layer.schemas.countries`), so application code gets type-safe hints instead of free-form strings.
- **Pillar answers**: Use `PillarAnswerRepository.create_pillar_answer(...)` (or replicate its guard) so tenant-scoped answers use the document owner (or the system sentinel) while still allowing ownerless/system-owned answers for shared documents. The published-only uniqueness leverages `coalesce(owner_user_id, sentinel)` to keep deduplication intact.

Keep this contract in mind when writing ingestion logic or creating fixtures—factories default to generating a tenant-scoped `owner_user_id`, so explicitly pass `owner_user_id=None` or the sentinel when building shared/system corpus rows.

## Access Control & Session Expectations

PostgreSQL no longer enforces Row-Level Security or custom `POLICY` objects for the shared data layer. Instead:

- Each environment provisions a dedicated database user/password; services authenticate using that credential and enforce per-tenant/base visibility in their own logic.

## Publication Year Backfill

- New uploads can pass `metadata.publication_year` (4-digit year) and ingestion will persist it on documents and chunks; invalid values are rejected.
- Existing documents can be populated via `shared_data_layer.scripts.backfill_publication_year` (dry-run by default, idempotent, uses filenames/URIs first and falls back to limited chunk text search).
- Recommended run path (from `packages/shared_data_layer`):
  - **Prod dry-run:**  
    `env_file=$(../../scripts/use_env.sh prod); set -a && source "$env_file" && set +a; uv run python -m shared_data_layer.scripts.backfill_publication_year --log-file ../../logs/publication_year_backfill_$(date +%s).log`
  - **Prod apply:** add `--apply` to the above command to commit changes.
  - **Local:** swap `use_env.sh local` and point `--database-url` if needed.
- Logs are written to the path passed via `--log-file`; prefer `logs/publication_year_backfill_<timestamp>.log` at the repo root for auditability.

## Embeddings, Deprecations, and Ownership Updates

- **Embedding dimension**: voyage-context-3 embeddings default to **1024** dims, configurable via `VOYAGE_EMBEDDING_DIM`/`VOYAGE_OUTPUT_DIMENSION`. The `Vector` columns, factories, and indexes reuse this shared dimension.
- **Non-text fields deprecated**: `chunks.image_caption`, `schema_summary`, `table_payload`, and `bbox` remain nullable but are unused in the text-only ingestion pipeline.
- **Graph/workflow tables deprecated**: `graph_*` and `workflow_*` tables persist for backward compatibility and are marked as deprecated; new text-only RAG flows should not write to them.
- **Ownership flexibility**: Documents may omit `owner_user_id` (even for non-base scopes) or use the system sentinel `00000000-0000-0000-0000-000000000000`. Base documents may set the sentinel or stay ownerless; pillar answers accept ownerless/system-owned records as well as matching tenant owners.
- Repository helpers (e.g., `DocumentRepository.attach_to_conversation`, `PillarAnswerRepository.create_pillar_answer`) validate owner identity, country scope, and dedup rules before issuing writes.
- Database constraints (unique indexes, check constraints, FK pairs, partitions) guarantee structural integrity, but they do **not** replace service-layer authorization.

When running manual SQL, keep in mind that all rows are visible to the connected role—scope queries explicitly by `owner_user_id`, `country_code`, or other filters if you need to mimic tenant-visible data.

## Partitioned Tables & Refresh Helpers

- `chunks` and `graph_entities` are LIST-partitioned. Graph entities ship eager partitions for `USA`, `GBR`, and `CAN`, and everything else (including tenant-specific rows) lands in `graph_entities_default`. The composite primary key `(id, country_code)` means every entity row now carries a concrete ISO-3 `country_code` value—even tenant-scoped data should use `MULT`/`UNK`/other explicit codes—so edges can reference the correct partition.
- `graph_edges` now store `source_entity_country_code` / `target_entity_country_code`, letting the FK target the composite key without chasing the ORM for derived metadata.
- `base_documents_by_country` is also LIST-partitioned. The cache now pre-creates partitions for **every** ISO-3166-1 alpha-3 country plus the `base_documents_by_country_default` catch-all, and `ensure_base_documents_partition()` still provisions new partitions if ISO ever expands.
- Use `SELECT refresh_base_documents_by_country(NULL)` for a full rebuild or pass a `country_code` to refresh a single partition. Python callers can also use `shared_data_layer.db.maintenance.refresh_all_base_documents_cache()` (global) or `refresh_base_documents_cache_for_country(session, "USA")` for targeted rebuilds—both wrap the same SQL helper.
- Knowledge-graph consumers can refresh both materialized views via:

  ```sql
  SELECT refresh_graph_materializations(false);
  ```

  Repositories expose `KnowledgeGraphRepository.refresh_materializations()` for async workflows.
  Operators can now run `python -m shared_data_layer.manage refresh-graph-mviews [--concurrently]` to execute the same helper outside the app tier after bulk ingestion jobs complete. Use `--concurrently` only when the unique indexes backing the materialized views already exist so the refresh can keep them readable.
- Community metrics also have a first-class refresh helper. Run `SELECT refresh_graph_communities(NULL, NULL, NULL);` (or target a specific country/algo/UUID) to rebuild `entity_ids`, `member_count`, `edge_count`, and `evidence_count`. Python callers can invoke `shared_data_layer.db.maintenance.refresh_graph_community_rollups(...)`, while operators can run `python -m shared_data_layer.manage refresh-graph-communities [--country-code USA --algo-version v2 --community-id <uuid>]` after bulk KG updates.
- Retrieval queries use the `active_chunks` materialized view instead of joining `documents` repeatedly. Run `REFRESH MATERIALIZED VIEW active_chunks;` (or `... CONCURRENTLY` when the unique `id` index is available) after document status/deletion changes that bypass the standard ingestion pipeline, or call the async helper `shared_data_layer.db.maintenance.refresh_active_chunks_view(session, concurrently=False)` from Python.

### Retrieval Chunk Partition Maintenance

- `chunks` is LIST-partitioned on `country_code` with dedicated tables for `chunks_usa`, `chunks_gbr`, and `chunks_can`, plus a `chunks_default` partition for everything else. These hot partitions keep country-specific workloads off the default heap.
- Retrieval workloads rely on multiple parent indexes—`GIN (text_tsv)`, `BRIN (created_at)`, `BRIN (updated_at)`, and both `IVFFLAT` + `HNSW` vector indexes on `embedding`. PostgreSQL automatically builds these indexes for the partitions that exist when the parent index is created.
- When you provision a new partition (for example, a `chunks_mex` table), you must create and attach the matching indexes so the partition participates in search plans:

  ```sql
  CREATE TABLE IF NOT EXISTS chunks_mex PARTITION OF chunks FOR VALUES IN ('MEX');
  CREATE INDEX chunks_mex_document_position_idx
    ON chunks_mex (document_id, chunk_type, position);
  ALTER INDEX ix_chunks_document_position ATTACH PARTITION chunks_mex_document_position_idx;

  CREATE INDEX chunks_mex_text_tsv_gin ON chunks_mex USING gin (text_tsv);
  ALTER INDEX ix_chunks_text_tsv_gin ATTACH PARTITION chunks_mex_text_tsv_gin;

  CREATE INDEX chunks_mex_created_at_brin ON chunks_mex USING brin (created_at);
  ALTER INDEX ix_chunks_created_at_brin ATTACH PARTITION chunks_mex_created_at_brin;

  CREATE INDEX chunks_mex_updated_at_brin ON chunks_mex USING brin (updated_at);
  ALTER INDEX ix_chunks_updated_at_brin ATTACH PARTITION chunks_mex_updated_at_brin;

  CREATE INDEX chunks_mex_embedding_ivfflat
    ON chunks_mex USING ivfflat (embedding vector_ip_ops) WITH (lists = 100);
  ALTER INDEX ix_chunks_embedding_ivfflat ATTACH PARTITION chunks_mex_embedding_ivfflat;

  CREATE INDEX chunks_mex_embedding_hnsw
    ON chunks_mex USING hnsw (embedding vector_ip_ops) WITH (m = 16, ef_construction = 64);
  ALTER INDEX ix_chunks_embedding_hnsw ATTACH PARTITION chunks_mex_embedding_hnsw;
  ```

- After attaching indexes, run `ANALYZE chunks_mex;` so query plans understand the new partition's statistics. No ORM changes are necessary because SQLAlchemy targets the parent table.

### Retrieval Telemetry Indexes

- `retrieval_runs.document_scope` now has `GIN (document_scope jsonb_path_ops)` plus an expression index on `(document_scope -> 'country_codes')` to accelerate audits that filter by included countries. These indexes are created via the base migration and verified in `tests/test_views.py::test_retrieval_runs_document_scope_indexes`.
- When writing custom queries, prefer `document_scope @> '{"country_codes":["USA"]}'::jsonb` so PostgreSQL can leverage the operator classes defined above.

## Observability Aids

- `document_gc_events` stores trigger-generated audit rows whenever `active_chat_refs` falls to zero or `deleted_at` changes. Query this table to power GC dashboards or alerting.
- `workflow_version_history` surfaces the approved version lineage for each workflow graph (graph metadata + change log + approver info).
- `workflow_version_diffs` compares consecutive versions of a graph, exposing node/edge counts, deltas, and raw change logs so reviewers can audit structural changes quickly.

## Operational Guardrails & Runbooks

### Extension Rationale

- We intentionally stick with vanilla PostgreSQL plus the core extensions that ship in every managed service (`pgcrypto`, `ltree`, `pg_trgm`, `vector`). They solve hashing, hierarchical paths, fuzzy search, and embedding search without introducing bespoke background daemons.
- Avoiding heavier add-ons (Citus, Timescale, custom GC extensions) keeps backup/restore, failover, and IAM consistent across every environment: the same SQL snapshot runs locally, in CI’s Testcontainers, and in production.
- Disaster recovery becomes a normal `pg_dump` + `pg_restore` flow because we never depend on external file systems or background workers owned by third-party extensions.

### Document GC Workflow

- Conversation attachment triggers keep `documents.active_chat_refs` accurate no matter how conversation rows are inserted or soft-deleted. When the count transitions to zero (or `deleted_at` toggles), a `document_gc_events` row with `event_type` of `active_refs_zero` or `deleted_state_changed` is inserted alongside before/after counters.
- Operators should poll `document_gc_events` (ordered by `created_at`) to drive downstream cleanup jobs:
  1. Query for the latest `active_refs_zero` per `document_id`.
  2. Re-validate the document still has `active_chat_refs = 0` (race-safe guardrail).
  3. Run the application-layer GC that purges orphaned chunks/artifacts.
  4. Soft delete the document (or mark the GC event as processed via service metadata) so future attachments can rehydrate it cleanly.
- Because the ledger lives entirely inside PostgreSQL you can replay GC decisions just by re-running the query or shipping the rows into observability—no external state machines required.

### Refresh Cadence & CLI Hooks

- **Base documents cache**: call `shared_data_layer.db.maintenance.refresh_base_documents_cache_for_country(session, "USA")` after ingesting new base corpus rows for a specific country or `refresh_all_base_documents_cache` for a global rebuild. Operators can run the same SQL directly: `SELECT refresh_base_documents_by_country(NULL);`.
- **Active chunks snapshot**: whenever documents skip the standard ORM hooks (bulk COPY, data backfill), invoke `refresh_active_chunks_view(session, concurrently=True)` or run `REFRESH MATERIALIZED VIEW CONCURRENTLY active_chunks;` to keep retrieval workloads consistent.
- **Graph materializations**: bulk KG imports should finish with `python -m shared_data_layer.manage refresh-graph-mviews [--concurrently]` followed by `python -m shared_data_layer.manage refresh-graph-communities` scoped to the affected country/algo. The helpers wire up the async session + transaction handling for you.
- **Community rollups**: downstream analytics that only care about a single community can pass `--community-id <uuid>` to the CLI or call `refresh_graph_community_rollups(session, community_id=...)` for precise recomputations.

### Partition & Index Maintenance

- `base_documents_by_country` eagerly provisions a partition per ISO alpha-3 code. If ISO expands, run `SELECT ensure_base_documents_partition('<NEW>');` (already invoked inside the refresh helper) and re-run the catalog audit tests (`pytest -k catalog`) to prove the new partition exists.
- Retrieval `chunks` and KG `graph_entities` tables require matching indexes on every new partition. Use the sample commands earlier in this README, then `ALTER INDEX ... ATTACH PARTITION ...` for each global index (`GIN`, `BRIN`, `IVFFLAT`, `HNSW`). Finish with `ANALYZE <partition>;`.
- When in doubt, inspect the parent catalog: `SELECT partstrat FROM pg_partitioned_table ...` and `SELECT indexname FROM pg_indexes ...`. The new pytest utilities (see below) automate these checks so schema drift is caught during CI.

### pgvector Tuning Cheat Sheet

- Default index definitions target `vector_ip_ops` with `lists = 100` for `ivfflat` and `m = 16`, `ef_construction = 64` for `hnsw`. These work well for ~100k chunks. Increase `lists` or `m` before reindexing if recall drops at higher scale.
- Query-side knobs: `SET ivfflat.probes = 10;` for low-latency approximate lookups, or bump toward 50–100 for higher recall. For HNSW searches, adjust `SET hnsw.ef_search = 64;` to trade CPU for accuracy.
- Always run `VACUUM ANALYZE chunks_<country>;` after bulk embedding imports so the planner keeps using vector indexes instead of falling back to sequential scans. If maintenance windows are tight, increase `maintenance_work_mem` during refresh jobs to accelerate index builds.

### Catalog Audits

- The automated guardrails live in `tests/test_catalog_audits.py` and rely on reusable helpers from `tests/catalog_utils.py`. They verify partition strategies, required partitions, and index definitions for every critical table.
- Run `./.venv/bin/pytest tests/test_catalog_audits.py -n auto` (or `pytest -k catalog`) whenever schema changes land. These checks run by default as part of the full suite, so migrations that drop/rename indexes will now fail fast.

## Workflow Guardrails

- The `ck_workflow_nodes_path_depth` constraint (plus the matching trigger) ensures every node's LTREE path respects the owning graph's `max_depth`, even when ORM hooks are bypassed.
- `trg_workflow_nodes_prevent_cycle` rejects ad-hoc updates that would move a node under its own descendants, preserving acyclic workflow trees outside of the `workflow_nodes_move_subtree` stored procedure.

## Linting & Formatting

This project uses `ruff` for linting and formatting, configured to match `flake8`, `isort`, and `black` (line length 88).

To check for linting errors:
```bash
.venv/bin/ruff check .
```

To fix linting errors automatically:
```bash
.venv/bin/ruff check --fix .
```

To format code:
```bash
.venv/bin/ruff format .
```

To run type checking:
```bash
.venv/bin/ty check .
```

### Writing Tests for Other Services
You can reuse the testing infrastructure provided by this package in other services.

**1. Setup `conftest.py`**

In your service's `tests/conftest.py`, import the shared fixtures. This ensures that a single Postgres container is spun up for the entire test session, and each test gets an isolated transaction.

```python
# tests/conftest.py
import pytest
# Import the shared fixtures to make them available in this test suite
from shared_data_layer.testing.conftest import (
    postgres_container,
    engine,
    session_factory,
    db_session,
    event_loop,
)
```

**2. Write an Integration Test**

You can now use `db_session` in your tests. It will automatically roll back changes after each test.

```python
# tests/test_my_service.py
import pytest
from shared_data_layer.testing.factories.users import UserFactory
from shared_data_layer.testing.factories.documents import DocumentFactory

@pytest.mark.asyncio
async def test_create_document_for_user(db_session):
    # 1. Setup data using factories
    user = await UserFactory.create_async(session=db_session)
    
    # 2. Perform action (e.g., call your service logic)
    # doc = await my_service.create_doc(user_id=user.id, ...)
    # For demonstration, we'll use the factory directly:
    doc = await DocumentFactory.create_async(session=db_session, owner_user_id=user.id)

    # 3. Verify
    assert doc.owner_user_id == user.id
    assert doc.id is not None
```



## Migrations

Migrations are managed via Alembic.

To generate a new migration (after modifying models):
```bash
# Ensure DATABASE_URL is set to a running DB instance
export DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
shared-data-layer migrate --autogenerate -m "Description of changes"
```

To apply migrations:
```bash
shared-data-layer migrate upgrade head
```
