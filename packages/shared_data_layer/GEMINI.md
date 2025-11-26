# Gemini Agent Context & Protocols

This `GEMINI.md` file provides specific context and instructions for Google Gemini models working on the `shared_data_layer` package. It serves as the **authoritative source of truth** alongside `AGENTS.md`.

## 🧠 Cognitive Workflow (Gemini Optimized)
You have a **long context window**. Use it to your advantage:
1.  **Ingest Context**: Before planning, read `README.md`, `pyproject.toml`, and `AGENTS.md` to ground your responses.
2.  **Plan**: Analyze the request. Identify which files need changes.
3.  **Research**: If you are unsure about a library (e.g., `polyfactory`, `ltree`, `pgvector`), use `context7` or `serper-search` **IMMEDIATELY**. Do not guess.
4.  **Act**: Make atomic changes. Focus on one file/module at a time.
5.  **Verify**: Run tests immediately after changes.

## 🛑 Stuck State Protocol (CRITICAL)
**Trigger**: If you fail to fix an error or implement a feature **3 times in a row**.

**Action**:
1.  **STOP** coding immediately.
2.  **Create a Reproduction Script**: Write a minimal standalone script in `tests/reproduce_issue.py` to isolate the failure.
3.  **Research**: Use `serper-search` and `context7` to find solutions.
    *   *Query Template*: "python <library_name> <error_message> solution"
    *   *Query Template*: "how to use <feature> in <library_name>"
4.  **Hypothesize**: Formulate a NEW approach based on research.
5.  **Implement**: Apply the new fix.

**Prohibited Behavior**:
- ❌ Do NOT blindly apply the same fix multiple times.
- ❌ Do NOT remove tests to "fix" failures.
- ❌ Do NOT apologize in the chat; just fix the issue.

## 🛠️ Environment & Execution
- **Package Manager**: Use `uv` strictly.
    - Install: `uv sync --all-extras`
- **Interpreter**: `.venv/bin/python`
- **Testing**: `.venv/bin/pytest`
    - Parallel: `.venv/bin/pytest -n auto`
    - Single Test: `.venv/bin/pytest tests/path/to/test.py::test_name`

## ✅ Definition of Done
You are NOT done until you have run these commands and they pass with **zero errors**:
1.  **Format**: `.venv/bin/ruff format .`
2.  **Lint**: `.venv/bin/ruff check --fix .`
3.  **Type Check**: `.venv/bin/ty check .` (Astral's Rust-based type checker)

## 🏗️ Architecture & Patterns

### Database & Migrations
- **Extensions**:
    - `ltree` (hierarchy)
    - `vector` (embeddings)
    - `pg_trgm` (similarity search)
    - `pgcrypto` (UUIDs/hashing)
    - *Note*: Enabled in `initial_migration`.
- **Migrations**: Located in `src/shared_data_layer/migrations`.
    - **Tests**: Migrations run automatically via `engine` fixture in `conftest.py`.
    - **Manual**: `alembic upgrade head`.
- **Stored Procedures**: `workflow_nodes_move_subtree` handles ltree moves.
    - **Quirk**: The SP requires explicit casting to `ltree` for updates: `SET path = (...)::ltree`.

### Pydantic & ORM (Asyncio Rules)
- **Problem**: SQLAlchemy Async models cannot lazy-load relationships outside an active session/loop. Pydantic validation triggers attribute access.
- **Rule**: You **MUST** eagerly load all relationships required by the Pydantic schema using `selectinload` or `joinedload` in the Repository layer.
- **Pattern**:
    ```python
    # ✅ GOOD (Repository)
    stmt = select(Course).options(selectinload(Course.modules))
    result = await session.execute(stmt)
    return result.scalar_one()
    
    # ❌ BAD
    # Returning model without loading relations -> Pydantic throws MissingGreenlet/LazyLoad error
    ```

### Testing Infrastructure
- **Container**: `PostgresContainerWithVector` (in `testing/containers.py`) is optimized with `fsync=off`, `synchronous_commit=off`, and `tmpfs` for performance.
- **Asyncio Scope**:
    - `pytest.ini` configures `asyncio_default_fixture_loop_scope = "session"`.
    - **Infrastructure Fixtures** (`event_loop`, `postgres_container`, `engine`) MUST be `scope="session"`.
    - **Data Fixtures** (`db_session`) should be `scope="function"` to ensure isolation (rollback after each test).

### Factories (`polyfactory`)
We use `polyfactory` for test data. Follow these strict patterns:

**1. Vectors (pgvector)**
*   **Problem**: `pgvector` fails if the embedding list is empty or has the wrong dimension.
*   **Solution**: Explicitly define the embedding field.
```python
# ✅ GOOD
class GraphEntityFactory(ModelFactory[GraphEntity]):
    embedding = Use(lambda: [0.0] * 512)

# ❌ BAD
class GraphEntityFactory(ModelFactory[GraphEntity]):
    ... # relying on default random generation often fails validation
```

**2. Ltree (Hierarchical Data)**
*   **Problem**: `ltree` paths must be valid strings (alphanumeric + dots).
*   **Solution**: Use a dedicated provider or validator.
    *   *Note*: `WorkflowNodeRead` schema has a validator for `Ltree`. `WorkflowNodeFactory` uses `Ltree` objects.

**3. Relationships**
*   **Problem**: Foreign key constraints fail if related objects aren't created first.
*   **Solution**: Explicitly build related objects in the factory.
```python
# ✅ GOOD
class GraphEdgeFactory(ModelFactory[GraphEdge]):
    source_node = Use(GraphEntityFactory.build)
    target_node = Use(GraphEntityFactory.build)
```

## 🐛 Common Issues & Fixes

| Error | Cause | Fix |
| :--- | :--- | :--- |
| `RuntimeError: Task ... attached to a different loop` | Fixture scope mismatch | Ensure infra fixtures are `session` scope. |
| `StatementError: expected 512 dimensions, not 0` | Empty embedding vector | Update Factory: `embedding = Use(lambda: [0.0] * 512)` |
| `ProgrammingError: column "path" is of type ltree` | SQL type mismatch | Cast explicitly in SQL: `SET path = (...)::ltree` |
| `MissingGreenlet` / `DetachedInstanceError` | Lazy loading in async | Use `options(selectinload(...))` in query. |

## 📂 Key Files Map
- **Fixtures**: `src/shared_data_layer/testing/conftest.py` (Session-scoped infra, Function-scoped session)
- **Containers**: `src/shared_data_layer/testing/containers.py` (Optimized Postgres container)
- **Factories**: `src/shared_data_layer/testing/factories/` (Polyfactory definitions)
- **Models**: `src/shared_data_layer/models/`
