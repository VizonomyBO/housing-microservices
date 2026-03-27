# WebSocket Service

Real-time status service for document approval reprocessing.

## Purpose

This service streams frontend-friendly status updates for:

- country reprocess state from `document_uploads`
- question-level cache state from `chat_response_cache`

It is designed to support:

- `ready -> stale -> reprocessing -> ready` question transitions
- upload lifecycle transitions `queued -> ingesting -> reprocessing_cache -> reprocessing_pdf -> done|failed`
- live progress updates while background worker jobs run

## Endpoints

- `GET /health`
- `WS /ws/reprocess/{country_code}`
- `WS /ws/reprocess/all`

## Authentication

The service accepts JWT via:

- `Authorization: Bearer <token>` header, or
- `?token=<jwt>` query parameter

Validation secret is resolved from:

1. `AUTH_SHARED_SECRET`
2. `JWT_SECRET_KEY` (fallback)

If no secret is configured, token validation is skipped.

## Message Shapes

Country subscription (`/ws/reprocess/{country_code}`):

```json
{
  "type": "reprocess_update",
  "country_code": "NPL",
  "overall_status": "queued",
  "upload_counts": {
    "queued": 1
  },
  "ingesting_progress": null,
  "questions": {
    "total": 50,
    "ready": 12,
    "stale": 37,
    "reprocessing": 1
  },
  "pdf_status": "pending"
}
```

`ingesting_progress` is present when an upload is currently in `ingesting`:

- `total_chunks`
- `total_batches`
- `processed_chunks`
- `processed_batches`
- `batch_size`

Global subscription (`/ws/reprocess/all`):

```json
{
  "type": "reprocess_update_all",
  "items": [
    {
      "type": "reprocess_update",
      "country_code": "NPL",
      "overall_status": "queued",
      "upload_counts": {
        "queued": 1
      },
      "questions": {
        "total": 50,
        "ready": 12,
        "stale": 37,
        "reprocessing": 1
      },
      "pdf_status": "pending"
    }
  ],
  "count": 1
}
```

## Local Run

From repo root:

```bash
cd services/websocket-service
uv sync --all-extras
uv run uvicorn websocket_service.main:app --host 0.0.0.0 --port 8091
```

Required env:

- `DATABASE_URL`

Optional env:

- `AUTH_SHARED_SECRET`
- `JWT_SECRET_KEY`
- `WEBSOCKET_POLL_INTERVAL_SECONDS` (default `2.0`)
- `WEBSOCKET_SERVICE_PORT` (default `8091`)

## Docker

The service is wired in:

- `docker-compose.yml`
- `docker-compose.ec2.yml`

Nginx proxy route:

- `/api/ws/` -> `websocket-service:8091`

Example proxied subscription:

- `ws://<host>/api/ws/ws/reprocess/NPL`
