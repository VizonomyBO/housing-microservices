# Technology Stack

## Backend

### Python Services (Agent API, Ingestion, Auth, User)
- **Language/runtime**: Python 3.13 managed with `uv`.
- **Frameworks**: FastAPI (Agent API, ingestion), Flask (auth, user).
- **ORM**: SQLAlchemy 2.x (async support for Agent API/ingestion).
- **Validation**: Pydantic v2.
- **Auth**: Argon2-cffi for hashing, PyJWT for tokens, Flask-Limiter for rate limits.
- **LLM/Retrieval**: LangGraph orchestration; Voyage embeddings (`voyage-3-large`) + `rerank-2.5` (required); MarkItDown for extraction.

### Shared Data Layer
- **Path**: `packages/shared_data_layer`
- **Role**: Centralized SQLAlchemy models, repositories, schemas, and fixtures.
- **Tests**: Uses Testcontainers; Agent API integration tests import its fixtures.

## Optional Frontend / Aggregator
- **Swagger Service**: TypeScript 5+ on Node.js 20 with Express + Swagger UI Express + Winston (not deployed by default).

## Database
- **PostgreSQL 16 + pgvector** for semantic search; drivers: `asyncpg` and `psycopg`.
- **Logical DBs**: `housing` (Agent/shared data layer) and `auth_db` (auth/user).

## Infrastructure & DevOps
- **Docker Compose** for local, hybrid dev (`docker-compose.ec2.yml`), and prod profiles (defaults AWS-first; LocalStack opt-in).
- **AWS**: EC2-hosted services; S3 used in prod (LocalStack mocked locally when available).
- **Patch deploys**: Hot-patch via `scp` + `docker cp` + compose restart (see AGENTS.md §7).
- **Fail-fast defaults**: OPENAI + Voyage, Valkey, and rate limiting are required unless explicit test-only bypass flags are set.

## Tooling
- **Dependency management**: `uv sync`, `uv add`, `uv lock`, `uv run`.
- **Lint/format/type/test**: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`.
- **Env selection**: `.env.local`, `.env.dev`, `.env.prod` via `scripts/use_env.sh`.
