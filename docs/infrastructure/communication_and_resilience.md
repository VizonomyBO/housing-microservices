# Communication & Resilience

## Overview
With the architectural shift to a co-located **FastAPI + LangGraph** service, "inter-service" communication is primarily internal (function calls). This document defines the resilience patterns for these internal interactions, as well as the external boundaries with the User Service and Async Workers.

## 1. Internal Communication (FastAPI ↔ LangGraph)
- **Mechanism**: Direct Python function calls / Awaitables.
- **Pattern**:
    - **FastAPI** acts as the "Shell", handling HTTP, Auth, and Rate Limiting.
    - **LangGraph** acts as the "Kernel", executing stateful agent workflows.
- **Resilience**:
    - **Timeouts**: The API layer enforces a global timeout (e.g., 60s) on LangGraph executions. If the graph takes longer, the API returns `504 Gateway Timeout`, but the graph *may* continue running in the background if configured as a detached task.
    - **Isolation**: Heavy compute (e.g., PDF generation) is offloaded to Async Workers (see [async_jobs.md](async_jobs.md)) to prevent blocking the API event loop.

## 2. External Communication

### 2.1 Upstream User Service
- **Protocol**: REST (HTTP/1.1) over TLS.
- **Format**: JSON.
- **Resilience**:
    - **Circuit Breaker**: If the User Service fails (e.g., 5xx errors), the Housing Service opens the circuit to fail fast and prevent cascading latency.
    - **Caching**: User profiles and permissions are cached (Valkey) for a short TTL (e.g., 5 mins) to reduce chatter.

#### Circuit Breaker Configuration
- **Library**: `pybreaker` (v1.0+)
- **Failure Threshold**: 5 consecutive failures
- **Timeout**: 60 seconds (circuit remains open before attempting recovery)
- **Half-Open Max Calls**: 3 (test calls to verify service recovery)
- **Metrics**: Circuit state (`open`, `half_open`, `closed`) exposed via Prometheus metrics
- **Integration**: Middleware wraps all User Service API calls

**Example Usage**:
```python
from pybreaker import CircuitBreaker

user_service_breaker = CircuitBreaker(
    fail_max=5,
    timeout_duration=60,
    name="user_service"
)
```

### 2.2 Async Workers
- **Protocol**: SQS (Standard Queues).
- **Resilience**:
    - **Backpressure**: Controlled by SQS `VisibilityTimeout` and the number of concurrent worker consumers.
    - **Dead Letter Queues (DLQ)**: Failed jobs are moved to DLQ after 3 retries.

## 3. Health Checks & Observability

### 3.1 Health Endpoints
- **`/health/live`**: Returns `200 OK` if the FastAPI process is running. Used by K8s/Load Balancer liveness probes.
- **`/health/ready`**: Returns `200 OK` only if:
    - Database (Postgres): `SELECT 1` query completes within 2s timeout
    - Vector DB: Health endpoint (`/health`) returns 200 within 2s
    - Cache (Valkey): `PING` command succeeds within 1s timeout
    - *Note*: Does NOT check upstream User Service (to avoid circular dependencies or startup deadlocks).

### 3.2 Observability
- **Tracing**: OpenTelemetry spans are generated for:
    - Incoming HTTP requests.
    - LangGraph node executions.
    - DB queries.
    - External API calls (User Service, LLM APIs).
- **Metrics**:
    - `http_requests_total`: Throughput.
    - `http_request_duration_seconds`: Latency.
    - `langgraph_node_duration_seconds`: Agent step latency.
    - `active_requests`: Concurrency.
