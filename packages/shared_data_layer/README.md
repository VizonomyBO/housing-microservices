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
- Python 3.9+
- PostgreSQL with `pgvector` extension

### Installation
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
# From the monorepo root or package root
pytest packages/shared_data_layer/tests
```

### Writing Tests for Other Services
You can reuse the testing infrastructure provided by this package in other services.

**`conftest.py` example:**

```python
import pytest
from shared_data_layer.testing.conftest import postgres_container, engine, db_session

# These fixtures will automatically spin up a Postgres container with pgvector
# and provide an isolated async session for each test.
```

**Using Factories:**

```python
from shared_data_layer.testing.factories.users import UserFactory
from shared_data_layer.testing.factories.documents import DocumentFactory

async def test_my_service(db_session):
    user = await UserFactory.create_async(session=db_session)
    doc = await DocumentFactory.create_async(session=db_session, owner_user_id=user.id)
    # ... test logic ...
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
