# Monorepo & Shared Data Layer Structure

This document defines the monorepo layout and the design of the shared data layer package that will be consumed by multiple services (API gateway, agent workers, offline tooling).

---

## 1. Top-Level Monorepo Layout

The project follows a Python-friendly monorepo structure. Shared logic is encapsulated in installable packages under `packages/`, and services live under `apps/`.

```text
.
├── services/                  # Microservices directory
│   ├── auth-service/          # Existing Auth Service
│   ├── user-service/          # Existing User Service
│   ├── agent-api/             # [NEW] FastAPI application (Agent API, orchestration)
│   │   ├── pyproject.toml
│   │   └── src/
│   │       └── agent_api/
│   └── agent-worker/          # [NEW] Agent runners / background workers
│       ├── pyproject.toml
│       └── src/
│           └── agent_worker/
├── packages/
│   └── shared_data_layer/     # Shared schema & persistence package (this document)
│       ├── pyproject.toml
│       ├── src/
│       │   └── shared_data_layer/
│       └── tests/
├── docs/                      # This repo: architecture, data, interfaces, etc.
│   ├── overview/
│   ├── data/
│   └── interfaces/
├── tools/                     # CI/CD helpers, scripts, linting configs
└── docker-compose.yml         # Local infra (Postgres, Redis, etc.)
```

### 1.1 Consumption Strategy

**Goal:** Treat `packages/shared_data_layer` as a **first-class Python package** that services can install in editable mode during development and as a normal versioned dependency in CI/CD and production.

Typical consumption patterns:

- **Development (editable install)** from monorepo root:

  ```bash
  pip install -e ./packages/shared_data_layer[dev,test]
  pip install -e ./services/agent-api
  pip install -e ./services/agent-worker
  ```

- **Service `pyproject.toml` example** (if using PDM/Poetry-style local path deps):

  ```toml
  [project]
  name = "agent-api"
  requires-python = ">=3.11"

  [project.dependencies]
  shared-data-layer = { path = "../../packages/shared_data_layer", develop = true }
  ```

- **Import paths** from services:

  ```python
  from shared_data_layer.db.session import DatabaseSessionManager
  from shared_data_layer.repositories.documents import DocumentRepository
  from shared_data_layer.repositories.knowledge_graph import KnowledgeGraphRepository
  from shared_data_layer.schemas.documents import DocumentRead
  from shared_data_layer.schemas.knowledge_graph import GraphEntityRead
  ```

The monorepo root remains the working directory for tooling (pytest, ruff, mypy, etc.) but each app and package is independently installable.

---

## 2. Shared Data Layer Package Design

The `shared_data_layer` package is the **single source of truth** for:

- SQLAlchemy models reflecting the logical schema in `data/schema_and_persistence.md`
- Alembic migrations
- Async session and engine lifecycle management
- Repository/query abstractions
- Shared testing utilities (testcontainers fixtures, base test classes, factories)

### 2.1 Internal Directory Structure

```text
packages/shared_data_layer/
├── pyproject.toml                  # Package metadata & dependencies
├── src/
│   └── shared_data_layer/
│       ├── __init__.py
│       ├── config/
│       │   └── settings.py         # Resolving DATABASE_URL, Alembic script location, etc.
│       ├── db/
│       │   ├── base.py             # DeclarativeBase, naming conventions, mixins
│       │   ├── session.py          # DatabaseSessionManager (async engine & sessionmaker)
│       │   └── models/             # SQLAlchemy models, grouped by bounded context
│       │       ├── __init__.py
│       │       ├── users.py        # User & identity models
│       │       ├── documents.py    # Documents, artifacts, ingestion jobs, conversation_documents
│       │       ├── retrieval.py    # Chunks, chunk metrics, retrieval runs/items
│       │       ├── knowledge_graph.py # Graph entities, edges, evidence, communities
│       │       ├── workflow.py     # Workflow graphs, nodes, edges, versions
│       │       ├── conversations.py # Conversations, messages, tool calls, citations, checkpoints
│       │       └── insights.py     # Pillar answers and async insights
│       ├── migrations/             # In-package Alembic environment
│       │   ├── alembic.ini         # Shipped config, points to this script directory
│       │   ├── env.py              # Async Alembic environment
│       │   ├── script.py.mako
│       │   └── versions/           # Auto-generated migration scripts
│       ├── repositories/           # Query / persistence patterns, no heavy domain logic
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── users.py
│       │   ├── documents.py
│       │   ├── retrieval.py
│       │   ├── knowledge_graph.py
│       │   ├── workflow.py
│       │   ├── conversations.py
│       │   └── insights.py
│       ├── schemas/                # Pydantic v2 DTOs
│       │   ├── __init__.py
│       │   ├── common.py
│       │   ├── users.py
│       │   ├── documents.py
│       │   ├── retrieval.py
│       │   ├── knowledge_graph.py
│       │   ├── workflow.py
│       │   ├── conversations.py
│       │   └── insights.py
│       └── testing/                # Reusable test infra for any consumer
│           ├── __init__.py
│           ├── conftest.py         # Re-exportable pytest fixtures
│           ├── containers.py       # testcontainers helpers
│           ├── base.py             # AsyncBaseTestCase
│           └── factories/          # Polyfactory-based factories
│               ├── __init__.py
│               ├── base.py
│               ├── users.py
│               ├── documents.py
│               ├── retrieval.py
│               ├── knowledge_graph.py
│               ├── workflow.py
│               └── files.py
└── tests/                          # Package's own test suite (uses testing/ utilities)
```

#### 2.1.1 Mapping to Logical Schema

The logical schema in `data/schema_and_persistence.md` is mapped into SQLAlchemy models as follows:

- `users.py`: `User` plus audit mixins used by downstream tables.
- `documents.py`: `Document`, `Artifact`, `ConversationDocument`, and `IngestionJob` — everything that manages uploads, deduplication, and attachment scope.
- `retrieval.py`: `Chunk`, `ChunkMetrics`, `RetrievalRun`, `RetrievalRunItem`, including pgvector columns and LIST partition metadata.
- `knowledge_graph.py`: `GraphEntity`, `GraphEdge`, `GraphEvidence`, `GraphCommunity`, and helper views/materialized views for evidence rollups.
- `workflow.py`: `WorkflowGraph`, `WorkflowNode`, `WorkflowEdge`, `WorkflowVersion`, plus helper constraints/triggers described in `schema_and_persistence.md §3.10`.
- `conversations.py`: `Conversation`, `Message`, `MessageToolCall`, `MessageCitation`, `AgentStateCheckpoint` — the LangGraph execution trace.
- `insights.py`: `PillarAnswer` and `PillarAnswerSource` for async analytics artifacts that outlive a single conversation.

Each module stays aligned with the logical schema so repositories can target a bounded context without guessing which file owns which table.

### 2.2 Repositories and Service Integration

Repositories live in `shared_data_layer.repositories` and encapsulate query logic. They provide an API tailored to the needs of API and agent services without leaking raw ORM details.

Examples:

- `DocumentRepository`:
  - `async def get_document_with_chunks(self, document_id: UUID) -> DocumentWithChunksRead`
  - `async def list_documents_for_country(self, country_code: str, include_base: bool = True) -> list[DocumentSummary]`

- `KnowledgeGraphRepository`:
  - `async def fetch_entity_with_neighbors(self, entity_id: UUID, depth: int = 2) -> GraphEntityRead`
  - `async def list_edges_for_scope(self, country_code: str, owner_user_id: UUID | None) -> list[GraphEdgeRead]`

- `WorkflowGraphRepository`:
  - `async def get_published_workflow(self, domain: str, country_code: str | None) -> WorkflowGraphRead`
  - `async def move_subtree(self, graph_id: UUID, source_path: str, target_parent_path: str) -> WorkflowGraphRead`

**Key principles:**

- API and agent apps depend on repository interfaces and Pydantic schemas, not on SQLAlchemy models directly.
- Repositories receive an `AsyncSession` (from `DatabaseSessionManager`) and return Pydantic DTOs or primitives.
- Complex joins, eager-loading strategies (`selectinload`, `joinedload`), and vector queries are localized to repository implementations.

---

## 3. Packaging & Editable Installs

The shared data layer package is built with a modern `pyproject.toml`-only layout (no `setup.py`), which is the current best practice for Python packaging.

### 3.1 pyproject.toml Layout (Shared Data Layer)

High-level structure:

```toml
[project]
name = "shared-data-layer"
version = "0.1.0"
description = "Shared async SQLAlchemy data layer for the Agentic monorepo"
requires-python = ">=3.11"
dependencies = [
  "sqlalchemy[asyncio]>=2.0.0",
  "asyncpg>=0.30.0",
  "alembic>=1.13.0",
  "pydantic>=2.7.0",
  "pgvector[psycopg2-binary]>=0.2.0",
]

[project.optional-dependencies]
dev = [
  "ruff",
  "mypy",
]
test = [
  "pytest",
  "pytest-asyncio",
  "pytest-xdist",
  "testcontainers[postgresql]>=4.0.0",
  "polyfactory>=2.0.0",
]

[build-system]
requires = ["setuptools>=64", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

### 3.2 Editable vs. Versioned Installs

- **Editable install** (local dev):

  ```bash
  cd <monorepo-root>
  pip install -e ./packages/shared_data_layer[dev,test]
  ```

- **Versioned install** (CI/CD and production):

  ```bash
  cd packages/shared_data_layer
  python -m build
  pip install dist/shared_data_layer-0.1.0-py3-none-any.whl
  ```

Apps should **never** vendor or duplicate models; they always import from `shared_data_layer`.

---

## 4. Async Session & Engine Management

A central piece of the shared data layer is the `DatabaseSessionManager` in `shared_data_layer/db/session.py`. It standardizes how services create and use async SQLAlchemy sessions.

### 4.1 Responsibilities

- Hold a process-wide `AsyncEngine` for a given `database_url`.
- Provide a `sessionmaker` for `AsyncSession`.
- Offer a simple async context manager to obtain an `AsyncSession`.
- Cleanly dispose the engine on application shutdown.
- Allow tests (via testcontainers) to **override** the engine/URL.

### 4.2 Example Public API

_Not implementation code, but the intended interface:_

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


class DatabaseSessionManager:
    _engine: Optional[AsyncEngine] = None
    _session_factory: Optional[sessionmaker[AsyncSession]] = None

    @classmethod
    async def init(cls, database_url: str, echo: bool = False, pool_size: int = 10) -> None:
        ...

    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncIterator[AsyncSession]:
        ...

    @classmethod
    async def dispose(cls) -> None:
        ...

    @classmethod
    async def override_engine(cls, engine: AsyncEngine) -> None:
        ...
```

Usage in **FastAPI gateway**:

```python
# services/agent-api/src/agent_api/db.py
from shared_data_layer.db.session import DatabaseSessionManager

async def init_db():
    await DatabaseSessionManager.init(settings.DATABASE_URL)

async def close_db():
    await DatabaseSessionManager.dispose()

async def get_db():
    async with DatabaseSessionManager.session() as session:
        yield session
```

Worker processes (agent runners) use the same pattern in their startup/shutdown hooks.

---

## 5. Alembic Migrations Inside the Package

Alembic is fully embedded in `shared_data_layer/migrations` so that:

- There is exactly **one canonical migration history**.
- Any service (API or worker) can run migrations for the shared schema.
- Migrations are versioned and shipped with the `shared_data_layer` wheel.

### 5.1 Layout

```text
shared_data_layer/migrations/
├── alembic.ini        # Configures script location, logging, etc.
├── env.py             # Async environment, uses SQLAlchemy 2.0 async engine
├── script.py.mako     # Template for new migration scripts
└── versions/          # Auto-generated migration scripts live here
```

### 5.2 Running Migrations from Services

We expose a thin wrapper that configures Alembic and runs migrations:

```python
# shared_data_layer/migrations/__init__.py

async def run_migrations(database_url: str) -> None:
    """
    Programmatically run Alembic migrations up to head against the given database URL.
    Intended to be called on service startup (API, workers).
    """
    ...
```

A CLI entry point is also provided via `pyproject.toml`:

```toml
[project.scripts]
shared-data-layer = "shared_data_layer.manage:main"
```

Example CLI usage from monorepo root:

```bash
# Using DATABASE_URL from environment
shared-data-layer migrate
```

The `manage.py`-style entry point:

- Reads `DATABASE_URL` from the environment (or accepts `--database-url`).
- Constructs an Alembic `Config` with `script_location` pointing inside the package.
- Calls `alembic.command.upgrade("head")` using an async engine (via `env.py`).

### 5.3 Version Parity Across Services

- All apps (API gateway, agent workers) depend on the **same version** of `shared-data-layer`.
- CI enforces that:
  - All migrations are applied before running tests.
  - No app pins an older version of `shared-data-layer` than the one used by migrations.

---

## 6. Pydantic v2 Integration & Type Safety

The shared data layer defines Pydantic v2 schemas in `shared_data_layer/schemas` that wrap SQLAlchemy models and are used as DTOs by services.

### 6.1 Base Schema Config

```python
from pydantic import BaseModel
from pydantic import ConfigDict

class ORMBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

Each domain module (`users.py`, `documents.py`, `knowledge_graph.py`, etc.) then defines its own:

- `UserCreate`, `UserUpdate`, `UserRead`
- `DocumentCreate`, `DocumentUpdate`, `DocumentRead`, `DocumentWithChunksRead`
- `ChunkRead`, `RetrievalRunRead`, `RetrievalRunItemRead`
- `GraphEntityRead`, `GraphEdgeRead`, `GraphCommunityRead`
- `WorkflowGraphRead`, `WorkflowNodeRead`, `WorkflowEdgeRead`

### 6.2 Avoiding Lazy Loading Pitfalls

Because SQLAlchemy async models require an event loop to lazy-load relationships, we must avoid hitting the database during Pydantic serialization.

Patterns:

- Repositories **always** eagerly load the graph they intend to serialize using `selectinload`/`joinedload`.
- Only after loading, they pass model instances into Pydantic schemas with `from_orm` / model instantiation:
  
  ```python
  result = await session.execute(query)
  document: Document = result.scalar_one()
  return DocumentWithChunksRead.model_validate(document)
  ```

- Tests and factories follow the same rule to avoid `MissingGreenlet` errors.

---

## 7. Testing Architecture (“The Django Way”)

This section describes the shared testing infrastructure provided by `shared_data_layer.testing`. It is designed to emulate the ergonomics of Django's `TestCase` / `TransactionTestCase` while using async SQLAlchemy and pytest.

### 7.1 Goals

- Provide a **single Postgres testcontainer** for the whole test session (by default) to keep tests fast.
- Ensure **full isolation per test** using transactional rollbacks (or table truncation where necessary).
- Export fixtures and base classes that both:
  - The `shared_data_layer` package tests can use.
  - Downstream services (API gateway, agent workers) can import and reuse.

### 7.2 Testcontainers Strategy

Default pattern:

- **One `PostgresContainer` per pytest session**:
  - Start container in a `session`-scoped fixture.
  - Build a database URL dynamically and expose it to tests.
  - Run Alembic migrations once at session startup.
- **Per-test isolation** via nested transactions:
  - Open a connection and begin a transaction per test.
  - Bind an `AsyncSession` to that connection.
  - Run the test.
  - Roll back the transaction in teardown.

Tradeoffs:

- This pattern is much faster than starting a container per test.
- If some tests need to mutate the schema or use operations incompatible with nested transactions, they can opt into:
  - Truncating tables between tests, or
  - Using a different fixture that creates a fresh database/schema.

### 7.3 Shared `conftest.py` in `shared_data_layer/testing`

`shared_data_layer/testing/conftest.py` exposes fixtures designed to be **imported** by consumer projects, not only used internally.

Representative fixtures (interface-level description):

- `postgres_container` (session-scoped):
  - Starts a `PostgresContainer` (`postgres:16` or `pgvector/pgvector:pg16`) using testcontainers.
  - Yields an object exposing a `get_connection_url()` method for async SQLAlchemy (using `asyncpg`).

- `database_url` (session-scoped):
  - Derives a SQLAlchemy-style async URL from `postgres_container`.

- `engine` (session-scoped):
  - Creates an `AsyncEngine` bound to `database_url`.
  - Applies Alembic migrations up to `head` before yielding.
  - Disposes the engine at session end.

- `session_factory` (session-scoped):
  - A `sessionmaker[AsyncSession]` bound to the shared engine.

- `db_session` (function-scoped):
  - For each test:
    - Opens a new connection.
    - Begins a transaction.
    - Binds an `AsyncSession` to the connection.
    - Yields the session to the test.
    - Rolls back the transaction on teardown.
    - Closes the connection.

Consumer apps can do:

```python
# apps/api_gateway/tests/conftest.py
pytest_plugins = [
    "shared_data_layer.testing.conftest",
]
```

or explicitly import fixtures and re-export them.

### 7.4 AsyncBaseTestCase

While pytest is function-based, some teams prefer class-based test patterns similar to Django's `TestCase`. The shared data layer provides an `AsyncBaseTestCase` in `shared_data_layer/testing/base.py` that integrates with pytest-asyncio.

Design:

- Implemented as a mixin using pytest markers and class-level fixtures.
- Provides class-level hooks that align with Django semantics:

  - `@classmethod async def async_set_up_class(cls): ...`
  - `@classmethod async def async_tear_down_class(cls): ...`

- Exposes convenience helpers:

  - `async def create_user(self, **overrides) -> User`
  - `async def create_document_with_chunks(self, owner: User | None, **overrides) -> Document`

These helpers internally:

- Use the `db_session` fixture.
- Call Polyfactory-based factories (see below) to construct and persist objects.
- Are designed so test classes can inherit from `AsyncBaseTestCase` and annotate `db` or `session` attributes with `AsyncSession`.

Example usage:

```python
import pytest
from shared_data_layer.testing.base import AsyncBaseTestCase

@pytest.mark.asyncio
class TestDocumentFlows(AsyncBaseTestCase):
    async def test_can_create_document_with_chunks(self, db_session):
        user = await self.create_user(session=db_session)
        document = await self.create_document_with_chunks(owner=user, session=db_session)
        assert document.chunks
```

### 7.5 Factories & Export for Consumers

#### 7.5.1 Library Choice: Polyfactory

We use **Polyfactory** (formerly `pydantic-factories`) because:

- It has first-class support for **Pydantic v2** and can also integrate with SQLAlchemy models.
- It leverages type hints to auto-generate realistic values.
- It minimizes boilerplate compared to `factory_boy` for Pydantic-heavy codebases.

#### 7.5.2 Factory Layout

Factories live in:

```text
shared_data_layer/testing/factories/
├── __init__.py
├── base.py             # Common helpers and base factory classes
├── users.py            # UserFactory
├── documents.py        # Document & artifact factories
├── retrieval.py        # Chunk & retrieval-run factories
├── knowledge_graph.py  # Graph entity/edge factories
├── workflow.py         # Workflow graph/node factories
└── files.py            # UploadedFile factories
```

Responsibilities:

- Construct fully valid SQLAlchemy model instances linked to an `AsyncSession`.
- Optionally return Pydantic DTOs directly if needed (e.g., in service-level tests).

Example interface:

```python
from uuid import UUID
from shared_data_layer.testing.factories import (
    UserFactory,
    DocumentFactory,
    GraphEntityFactory,
)

async def test_uses_factories(db_session):
    user = await UserFactory.create_async(session=db_session, email="admin@example.com")
    document = await DocumentFactory.create_with_chunks_async(session=db_session, owner=user)
    entity = await GraphEntityFactory.create_async(session=db_session, owner_user_id=user.id)
    assert isinstance(user.id, UUID)
    assert document.chunks
    assert entity.country_code
```

`shared_data_layer/testing/__init__.py` will **re-export** the main factories:

```python
from .factories.users import UserFactory
from .factories.documents import DocumentFactory, DocumentChunkFactory
from .factories.retrieval import RetrievalRunFactory
from .factories.knowledge_graph import GraphEntityFactory, GraphEdgeFactory
from .factories.workflow import WorkflowGraphFactory
from .factories.files import UploadedFileFactory

__all__ = [
    "UserFactory",
    "DocumentFactory",
    "DocumentChunkFactory",
    "RetrievalRunFactory",
    "GraphEntityFactory",
    "GraphEdgeFactory",
    "WorkflowGraphFactory",
    "UploadedFileFactory",
]
```

Consumer apps can then import directly:

```python
from shared_data_layer.testing import DocumentFactory, GraphEntityFactory, WorkflowGraphFactory
```

### 7.5.3 Combining Shared & App-Specific Factories

Consuming services:

- Reuse shared factories for core schema entities (user, document, graph, workflow, etc.).
- Layer on top their own factories for app-specific models, pointing them at the **same `db_session`** fixture:

```python
# services/agent-api/tests/factories/api_tokens.py
class ApiTokenFactory(...):
    @classmethod
    async def create_async(cls, session: AsyncSession, user: User, **kwargs) -> ApiToken:
        ...
```

This ensures that:

- All test data is created against the same database and transaction lifecycle.
- Services retain flexibility for their own domain needs without duplicating schema definitions.

---

## 8. Summary

- The monorepo is organized into `services/` (applications), `packages/` (shared libraries), `docs/`, and `tools/`.
- `packages/shared_data_layer` is the canonical home of:
  - Async SQLAlchemy 2.0 models and engine/session management.
  - Alembic migrations stored **inside** the package.
  - Pydantic v2 DTOs and repositories used by API and agent services.
  - Shared testing utilities, including testcontainers fixtures, `AsyncBaseTestCase`, and Polyfactory factories.
- Services consume the shared data layer both in editable mode during development and as a versioned wheel in CI/production, ensuring a single source of truth for schema and persistence behavior.
