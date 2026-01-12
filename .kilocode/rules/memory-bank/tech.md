# Technology Stack

## Backend

### Python Services (Agent API, Ingestion, Auth, User)
- **Language/runtime**: Python 3.13 managed with `uv`.
- **Frameworks**: FastAPI (Agent API, ingestion), Flask (auth, user).
- **ORM**: SQLAlchemy 2.x (async support for Agent API/ingestion).
- **Validation**: Pydantic v2.
- **Auth**: Argon2-cffi for hashing, PyJWT for tokens, Flask-Limiter for rate limits.
- **LLM/Retrieval**: LangChain v1 `create_agent` ReAct loop running on LangGraph runtime + MemorySaver checkpointing; Voyage embeddings (`voyage-context-3`/`voyage-3-large`) and `rerank-2.5` via langchain-voyageai; LangChain RecursiveCharacterTextSplitter for chunking; MarkItDown for extraction; hybrid BM25+vector via shared data layer repos.

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
- **Docker Compose** for local (LocalStack-first), dev-reload, and hybrid (`docker-compose.ec2.yml`) profiles. `docker-compose.dev.yml` bind-mounts code and runs uvicorn reload so rebuilds are only needed on dependency changes.
- **AWS**: EC2-hosted services; S3 used in prod (LocalStack mocked locally for dev). Deploy via `scripts/deploy_stack.sh --mode services-only|full-redeploy`; smokes via `scripts/local_smoke.sh --target prod` or `scripts/prod_deploy_and_smoke.sh`.
- **Patch deploys**: Hot-patch via `scp` + `docker cp` + compose restart (see AGENTS.md §7).
- **Fail-fast defaults**: OPENAI + Voyage, Valkey, and rate limiting are required unless explicit test-only bypass flags are set.

## Tooling
- **Dependency management**: `uv sync`, `uv add`, `uv lock`, `uv run`.
- **Lint/format/type/test**: `uv run ruff format .`, `uv run ruff check --fix .`, `uv run ty check .`, `uv run pytest -n auto`.
- **Env selection**: `.env.local`, `.env.dev`, `.env.prod` via `scripts/use_env.sh`.
