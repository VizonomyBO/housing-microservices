# Monorepo & Shared Data Layer

## Layout (current)
```
.
├── services/
│   ├── agent-api/          # FastAPI ReAct agent + tools (Pyodide sandbox)
│   ├── ingestion-service/  # FastAPI synchronous ingestion (MarkItDown → Voyage embeddings)
│   ├── auth-service/       # Flask JWT issuance/validation (auth_db)
│   └── user-service/       # Flask user management (auth_db)
├── packages/
│   └── shared_data_layer/  # Authoritative models/repos/migrations
├── docs/                   # Architecture, agents, runbooks, testing
├── scripts/                # use_env.sh, deploy_stack.sh, prod_smoke_check.sh, etc.
├── docker-compose.yml      # Local dev stack (Postgres, LocalStack, services)
├── docker-compose.ec2.yml  # Hybrid/dev stack pointed at remote infra
└── task_prompts/           # Archived task briefs (see deprecation notes)
```

## Shared data layer (authoritative schema)
- Lives in `packages/shared_data_layer`; install in editable mode from repo root when developing services.
- Owns SQLAlchemy models, Alembic migrations, repositories, and testing fixtures.
- Graph/workflow tables remain for backward compatibility but are **deprecated**; keep relations nullable and document them rather than deleting the package.
- Retrieval tables (`documents`, `chunks`, `chunk_metrics`, `retrieval_runs/items`, `conversations`, `agent_state_checkpoints`, etc.) back the ingestion-first flow; only add new fields through this package.

## Service consumption
- Python tooling uses uv on Python 3.13; run commands with `uv run ...`.
- Agent API imports repositories/models directly from `shared_data_layer` for persistence and retrieval.
- Ingestion service writes documents/chunks via the same package to keep pgvector dimensions and schema aligned.
- Auth/User services target the separate `auth_db` schema; do not mingle with `housing`.

## Notes
- Swagger/telemetry/cache helpers from earlier iterations are deprecated; keep references labeled as archived.
- Local dev requires LocalStack for AWS mocks; production bypasses LocalStack and runs on EC2 via `scripts/deploy_stack.sh`.
