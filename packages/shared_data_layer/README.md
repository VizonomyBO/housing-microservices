# Shared Data Layer

The `shared_data_layer` package serves as the single source of truth for database models, data access patterns (repositories), and data transfer objects (schemas) for the Housing Microservices project. It is built with **SQLAlchemy 2.0 (Async)**, **Pydantic V2**, and **PostgreSQL** with `pgvector` support.

## Project Structure

The package is organized as follows:

- **`src/shared_data_layer/db/models/`**: SQLAlchemy database models.
    - `users.py`: User management.
    - `documents.py`: Documents, Chunks, Artifacts.
    - `retrieval.py`: Retrieval runs and metrics.
    - `knowledge_graph.py`: Graph entities and edges.
    - `workflow.py`: Workflow definitions and versions.
- **`src/shared_data_layer/repositories/`**: Async repositories for data access.
    - `base.py`: Generic `BaseRepository` with common CRUD operations.
    - `documents.py`, `knowledge_graph.py`, etc.: Specialized repositories.
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

## Identity & Ownership Contract

- `owner_user_id` is **mandatory** for every document whose `access_scope` is not `base`. The database enforces this constraint and the `DocumentRead` schema validates it as well.
- Base documents must omit `owner_user_id` and provide an ISO-3 `country_code`. This value is propagated automatically to child rows (chunks, artifacts) through triggers.
- Pydantic schemas expose these ISO codes via the `CountryISOAlpha3` enum (`shared_data_layer.schemas.countries`), so application code gets type-safe hints instead of free-form strings.

Keep this contract in mind when writing ingestion logic or creating fixtures—factories now default to generating a tenant-scoped `owner_user_id`, so explicitly pass `owner_user_id=None` when building base corpus rows.

## Row-Level Security & Session Settings

RLS is enabled for documents, chunks, knowledge-graph entities/edges, workflow graphs, and GC events. Access is controlled via custom PostgreSQL settings:

- `SET app.bypass_rls = 'on'|'off'`: defaults to `on`. Turn it `off` to enforce policies.
- `SET app.current_owner_id = '<uuid>'`: grants access to tenant-scoped rows for the matching owner.
- `SET app.current_country_code = 'USA'`: grants access to base rows for the given country (upper-case ISO-3).

Example (tenant scoped):

```sql
SET app.bypass_rls = 'off';
SET app.current_owner_id = '4f1c59b6-3e2e-4d41-b883-4bd9a48a6e18';
SELECT * FROM documents;
```

Remember to `RESET` the settings (or set `app.bypass_rls = 'on'`) after running scoped queries in tests.

## Partitioned Tables & Refresh Helpers

- `chunks`, `graph_entities`, and `base_documents_by_country` are LIST-partitioned. The base-doc cache now pre-creates partitions for **every** ISO-3166-1 alpha-3 country plus the `base_documents_by_country_default` catch-all, and `ensure_base_documents_partition()` still provisions new partitions if ISO ever expands.
- Use `SELECT refresh_base_documents_by_country(NULL)` for a full rebuild or pass a `country_code` to refresh a single partition. Python callers can also use `shared_data_layer.db.maintenance.refresh_all_base_documents_cache()` (global) or `refresh_base_documents_cache_for_country(session, "USA")` for targeted rebuilds—both wrap the same SQL helper.
- Knowledge-graph consumers can refresh both materialized views via:

  ```sql
  SELECT refresh_graph_materializations(false);
  ```

  Repositories expose `KnowledgeGraphRepository.refresh_materializations()` for async workflows.

## Observability Aids

- `document_gc_events` stores trigger-generated audit rows whenever `active_chat_refs` falls to zero or `deleted_at` changes. Query this table to power GC dashboards or alerting.
- `workflow_version_history` surfaces the approved version lineage for each workflow graph (graph metadata + change log + approver info).

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
