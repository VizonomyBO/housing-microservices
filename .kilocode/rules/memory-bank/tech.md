# Technology Stack

## Backend

### Python Services (Agent API, Ingestion, Auth, User)
-   **Language**: Python 3.11+
-   **Frameworks**:
    -   **FastAPI**: Agent API, Ingestion Service (High performance, async).
    -   **Flask**: Auth Service, User Service (Mature, stable).
-   **ORM**: SQLAlchemy 2.0 (Async support).
-   **Data Validation**: Pydantic V2.
-   **Authentication**:
    -   **Argon2-cffi**: Password hashing.
    -   **PyJWT**: Token management.
-   **AI/LLM**: LangGraph (Agent orchestration).
-   **Document Processing**: MarkItDown.

### Shared Data Layer
-   **Path**: `packages/shared_data_layer`
-   **Role**: Centralized models, repositories, and schemas.
-   **Dependencies**: SQLAlchemy, Pydantic, Alembic.

## Frontend / Aggregator

### Swagger Service
-   **Language**: TypeScript 5.3+
-   **Runtime**: Node.js 20+
-   **Framework**: Express.js
-   **Documentation**: Swagger UI Express.
-   **Logging**: Winston.

## Database

### PostgreSQL
-   **Version**: 16
-   **Extensions**: `pgvector` (Vector embeddings for semantic search).
-   **Drivers**: `asyncpg` (Async Python driver), `psycopg2` (Sync Python driver).

## Infrastructure & DevOps

### Containerization
-   **Docker**: Service containerization.
-   **Docker Compose**: Orchestration for local, dev, and prod environments.

### Cloud (AWS)
-   **Compute**: EC2 (Production deployment).
-   **Storage**: S3 (Document storage - mocked by LocalStack locally).
-   **Mocking**: LocalStack (AWS services mock for local dev).

### Tooling
-   **Dependency Management**: `uv` (Fast Python package installer and resolver).
-   **Linting/Formatting**: `ruff`.
-   **Type Checking**: `mypy` / `ty`.
-   **Testing**: `pytest` (with `pytest-xdist` for parallel execution).

## Development Environment

### Setup
-   **Env Files**: `.env.local`, `.env.dev`, `.env.prod`.
-   **Scripts**: `scripts/` directory contains helpers for env setup, deployment, and smoke testing.

### Quality Gates
-   `ruff format .`
-   `ruff check --fix .`
-   `ty check .`
-   `pytest -n auto`
