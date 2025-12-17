# Asynchronous Jobs & Queues

> **Archived (pre-revamp):** Covers the deprecated SQS/Step Functions/Lambda worker stack. The current platform is synchronous ingestion-first (FastAPI) with no worker fleet or cache/rate-limiter layer. See `docs/overview/system_architecture.md` for the supported model.

## Overview
This document outlines the architecture for asynchronous background processing in the Housing Service. We use message queues (e.g., SQS) to decouple ingestion, PDF generation, and other long-running tasks from the main API request/response cycle.

### Reduced Scope Runtime (Task 3.5.3)
For the demo build, `services/agent-api` exposes a `ReducedScopeWorkerRuntime` that executes ingestion completion, pillar generation, and artifact creation inline. Instead of launching SQS/SFN workers, FastAPI routes and the Typer CLI call these helpers directly:

- `uv run python -m agent_api.cli run-ingestion --document-id <uuid>`
- `uv run python -m agent_api.cli generate-pillars --country-code LBR` (or `--conversation-id ...`)
- `uv run python -m agent_api.cli generate-artifact --conversation-id ... --artifact-type chat_export`

Each helper writes to the same tables (`ingestion_jobs`, `pillar_answers`, `pillar_answer_sources`, `artifacts`) and stubs PDF generation with `metadata.reduced_scope.status="skipped"`. When re-enabling the async workers, flip `REDUCED_SCOPE_ENABLED=0`, restore the queue consumers, and update the CLI/route docs to point back to the SQS pipelines described below.

## Job Types & Payloads

### 1. Ingestion & Embedding
- **Trigger**: New document upload or update.
- **Payload**:
  ```json
  {
    "job_id": "uuid",
    "type": "ingest_document",
    "user_id": "uuid",
    "document_id": "uuid",
    "s3_key": "path/to/file.pdf",
    "metadata": { ... }
  }
  ```
- **Processing**:
  1. Fetch file from S3.
  2. Parse text (e.g., via Unstructured or LlamaParse).
  3. Chunk text.
  4. Generate embeddings.
  5. Upsert to Vector DB.
  6. Update document status to `ready`.

### 2. PDF Export
- **Trigger**: User requests a chat history or report export.
- **Payload**:
  ```json
  {
    "job_id": "uuid",
    "type": "export_pdf",
    "user_id": "uuid",
    "conversation_id": "uuid",
    "options": { "include_citations": true }
  }
  ```
- **Processing**:
  1. Fetch conversation history and referenced documents.
  2. Render HTML template.
  3. Convert HTML to PDF.
  4. Upload PDF to S3 (presigned URL).
  5. Notify user (via WebSocket or polling status).

## Queue Configuration
- **VisibilityTimeout**:
    - **Ingestion Queue**: 900s (15 minutes) - Allows for PDF parsing, chunking, and embedding generation
    - **Export Queue**: 300s (5 minutes) - PDF generation is faster
    - **Rationale**: Set to 6x average processing time per AWS best practices
- **Deduplication**:
  - **Ingestion**: Use `document_hash` as the deduplication ID to prevent redundant processing of the exact same file content.
  - **Exports**: Use `conversation_id` + `timestamp` (quantized) to debounce rapid export requests.
- **Retry Policy**:
  - **Max Retries**: 3
  - **Backoff**: Exponential (30s, 60s, 120s).
  - **DLQ (Dead Letter Queue)**: Failed jobs after max retries are moved to a DLQ for manual inspection.

## Ref-Counting & Garbage Collection
- **Payload References**: Job payloads MUST reference the `document_id` and `user_id`.
- **Locking**: While an ingestion job is running, the associated `document_id` should be marked as `processing` to prevent premature deletion or modification.
- **Consistency**: Async jobs must respect the same visibility rules as the API. If a user deletes a document while it's being ingested, the job should check for existence before final commit or handle the "not found" error gracefully.

## Complex Workflows (LangGraph Integration)
For multi-step async workflows that require state persistence or human-in-the-loop interaction (e.g., resolving ambiguous document parsing), we leverage **LangGraph's `interrupt` and `checkpoint` mechanisms**.
- **Pattern**: The async worker can trigger a LangGraph workflow. If the workflow hits a decision point requiring user input, it calls `interrupt`, persisting its state.
- **Resumption**: When the user provides feedback (via API), the workflow is resumed using a `Command` with the new input, continuing from the exact point of interruption.

### LangGraph Checkpoint Configuration
To enable state persistence and resumption for multi-step async workflows:

- **Backend**: PostgreSQL (via `langgraph-checkpoint-postgres` package)
- **Table**: `langgraph_checkpoints` (auto-created by checkpointer)
- **Connection**: Uses same Postgres instance as main application database (separate schema: `langgraph`)
- **Retention Policy**:
    - Completed workflows: 30 days
    - Interrupted workflows (awaiting user input): Indefinite (manual cleanup via admin API)
- **Thread ID Strategy**:
    - Chat workflows: `conversation_id`
    - Async jobs: `job_id`
    - Format: UUID v4

**Installation**:
```bash
pip install langgraph-checkpoint-postgres
```

**Example Usage**:
```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn_string="postgresql://...")
graph = workflow.compile(checkpointer=checkpointer)
```

## Monitoring & Alerting
- **Metrics**:
  - `queue_depth`: Number of visible messages.
  - `job_latency`: Time from enqueue to completion.
  - `error_rate`: Percentage of failed jobs.
- **Alerts**:
  - High DLQ volume (> 10 messages/hour).
  - Processing lag (> 5 minutes for high-priority queues).
