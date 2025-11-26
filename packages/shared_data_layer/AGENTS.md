# Agent Guide for Shared Data Layer

This document provides context and instructions for AI agents working on the `shared_data_layer` package.

## Environment & Execution
- **Setup**: Use `uv` strictly. Run `uv sync --all-extras` to install everything. Do NOT use `pip` or `requirements.txt`.
- **Interpreter**: Use the virtual environment directly: `.venv/bin/python`.
- **Testing**: Use `.venv/bin/pytest`.
- **Parallel Execution**: Tests support parallel execution: `.venv/bin/pytest -n auto`.

## Definition of Done
After any task is considered finished, you **MUST** run the following commands to ensure the codebase is correctly linted and typed:
1.  **Format**: `.venv/bin/ruff format .`
2.  **Lint**: `.venv/bin/ruff check --fix .`
3.  **Type Check**: `.venv/bin/ty check .`

If any of these commands report errors, you **MUST** fix them before considering the task finally done.

## Testing Infrastructure
- **Container**: `PostgresContainerWithVector` (in `testing/containers.py`) is optimized with `fsync=off` and `tmpfs` for performance.
- **Asyncio**: `pytest-asyncio` is configured for `session` scope in `pytest.ini`.
    - **Critical**: All async fixtures must be `scope="session"` to avoid `RuntimeError: Task attached to a different loop`.
- **Factories**: We use `polyfactory`.
    - **Ltree**: `WorkflowNodeFactory` uses `Ltree` objects. `WorkflowNodeRead` schema has a validator for `Ltree`.
    - **Vectors**: `GraphEntityFactory` must explicitly set embedding: `embedding = Use(lambda: [0.0] * 512)` to avoid `StatementError` with `pgvector`.
    - **Relationships**: `GraphEdgeFactory` explicitly builds source/target using `GraphEntityFactory.build`.

## Database & Migrations
- **Extensions**: `ltree` and `vector` extensions are enabled in `initial_migration`.
- **Stored Procedures**: `workflow_nodes_move_subtree` handles ltree moves.
    - **Quirk**: The SP requires explicit casting to `ltree` for updates: `SET path = (...)::ltree`.
- **Alembic**: Migrations are in `src/shared_data_layer/migrations`.
    - Run migrations: `alembic upgrade head` (handled automatically by `engine` fixture in tests).

## Common Issues & Fixes
- **`RuntimeError: Task <...> got Future <...> attached to a different loop`**:
    - **Cause**: Fixture or test running in a different event loop.
    - **Fix**: Ensure `pytest.ini` has `asyncio_default_fixture_loop_scope = session` and fixtures use `scope="session"`.
- **`StatementError: (builtins.ValueError) expected 512 dimensions, not 0`**:
    - **Cause**: `GraphEntityFactory` generating empty list for embedding.
    - **Fix**: Use `embedding = Use(lambda: [0.0] * 512)`.
- **`ProgrammingError: column "path" is of type ltree but expression is of type text`**:
    - **Cause**: Stored procedure trying to update `ltree` column with `text`.
    - **Fix**: Cast to `::ltree` in SQL.

## Key Files
- `src/shared_data_layer/testing/conftest.py`: Session-scoped fixtures (`engine`, `db_session`).
- `src/shared_data_layer/testing/containers.py`: Optimized Postgres container.
- `src/shared_data_layer/testing/factories/`: Polyfactory definitions.
